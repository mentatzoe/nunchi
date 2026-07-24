# Implementation Plan: Nunchi V2 End-to-End Parity

> **Reference only.** Architecture and integration decisions remain useful.
> SpecKit, lifecycle, assignment, worktree, task, candidate, handoff, and
> acceptance instructions in this document are retired. Follow
> `docs/v2-delivery.md`.

**Branch**: `integration/v2` | **Date**: 2026-07-11 | **Spec**: `spec.md`

**Input**: The repository-owned selected design at
`docs/architecture/v2-selected-design.md` and contract reference at
`docs/contracts/nunchi-v2.md`, preserving Aleph Vault provenance `bdd1ebb` and
`c834e8c`, plus Zoe's 2026-07-20 implementation clarification on
live-conversation freshness and provenance-bound privileged actions.

**Program**: `001-nunchi-v2-program`

**Accountable owner lane**: `v2-program-owner`

**Declaration reset observation**: 2026-07-11 — program `READY`, authority
`NOT_GRANTED`, assignment `UNASSIGNED`; the values below are live declarations,
superseded only by immutable activation/acceptance evidence and append-only
candidate/handoff attempts

**Program state**: `DELIVERY`

**Program implementation authority**: `GRANTED`

**Assigned program participant / source (declaration)**: Codex — evidence/governance/assignments/codex-v2-program-owner-2026-07-24.md

**Implementation authorization**: `evidence/governance/v2-implementation-authorization.md`

**Current delivery baseline**:
`evidence/v2/completion-baseline-2026-07-23.md` — slice `010` accepted through
A1/A2 at effective commit
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`; required `I-010F` A3 pending;
slices `020`–`110` `PLANNED`; V1 current

**Upstream dependencies**: repository-owned selected design (Vault provenance
`c834e8c`); Constitution 2.5.0; the
ordinary-path V1 inventory and evidence baseline

## Summary

Deliver one coherent V2 product. The program fixes portable interface ownership
in slice `010`, separates truthful factual current observation and high-water
facts (`020`) from model pre-attention (`030`), and joins them with the fresh
conversation scheduler, normal participant turn, and deterministic
privileged-action guard (`040`). Transport,
harness, and adapter surfaces then implement the shared behavior without local
FIFO queues or permission conventions. Security/provenance (`100`) audits the
exact assembled implementation, and parity/cutover (`110`) freezes, reviews,
and integrates the sole final candidate.

The future product cutover is deliberately breaking and atomic. It replaces the
current V1 `PASS / ACK / ASK / SPEAK` lifecycle with participant-shaped
`SUPPRESS / WAKE / DEFER`, separate operational `ERROR`, compact factual
context, optional participant-owned expansion, and a direct act-or-silence
participant turn. It does not add a V1 bridge, a social ledger, or a send-time
social reclassification. Incoming messages are observations rather than queued
response obligations. Privileged actions require exact authenticated origin,
scoped capability, execution-time recheck, and an immutable action decision;
social or participant model output can propose but never authorize them.

## Technical Context

**Language/Version**: Python `>=3.11`, matching `pyproject.toml`

**Primary Dependencies**: zero required runtime dependencies for the shared
core; existing optional surface dependencies remain surface-owned. Authorized
slice implementation may change an optional dependency only through its owning
slice and the integrator.

**Storage**: bounded in-memory or native-history-backed observation continuity;
one ephemeral replaceable pending anchor per active participant/room; trusted
host capability policy and immutable action audit; no participant registry,
social ledger, response queue, or obligation store

**Testing**: Python `unittest`, deterministic contract/integration tests,
burst/coalescing and restart/backlog tests, authorization adversarial tests,
committed replay corpora, live delayed-participant acceptance scenes, and
installed-runtime probes

**Target Platform**: Python library and CLI; Hermes, Claude Code, Codex,
Discord-MCP, and in-tree standalone channel adapters

**Project Type**: library + CLI + adapter/harness integrations

**Performance Goals**: hard event/byte budgets on attention and participant
packets; at most one active turn plus one replaceable pending anchor per
participant/room; no message-by-message catch-up after a burst or restart;
receipts expose serialized bytes and model-specific token estimates; defaults
are selected from replay evidence rather than asserted here

**Constraints**: one logical pre-attention judgment; only a participant-shaped
model may socially suppress; uncertainty widens waking; exact transport facts
only for deterministic non-events; no send-time social classifier; operational
error wakes by default when a valid snapshot exists; no fabricated wake without
a safe room snapshot; no room- or model-controlled identity, policy, grant,
credential, endpoint, executable, or capability; privileged execution is
deterministically denied or sent to explicit approval when exact authorization
is absent; no mixed V1/V2 in-tree state

**Scale/Scope**: eleven implementation work packets, twelve canonical
interfaces, eighteen common acceptance scenes, one accountable integration
owner, and one frozen final candidate

## Constitution Check

*GATE: passed for planning acceptance; MUST be re-checked at slice activation
and every handoff.*

| Principle | Program proof | State |
|---|---|---|
| I. Selected V2 boundary | The program plans pre-attention and direct participant turns without reply composition or floor allocation. | PASS |
| II. Human-shaped judgment | Only `I-030A` may issue social suppression; deterministic transport work is limited to exact non-events. | PASS |
| III. Truthful identity/observation | `020` owns exact self binding, native relations, bounded coverage, honest continuation, and factual current snapshot/high-water facts; it owns no turn scheduler or response queue. | PASS |
| IV. Different owners | `030` decides attention; `040` owns coalesced opportunity scheduling, invokes a normal participant turn, and separately enforces privileged action authorization; no send reclassification is planned. | PASS |
| V. Atomic parity | `110` is the sole cutover sink and rejects mixed V1/V2 consumers or translation bridges. | PASS |
| VI. Evidence before claims | Every slice binds shared scenes to deterministic, replay, live, and provenance evidence as appropriate. | PASS |
| VII. Control-plane only | This tree contains planning Markdown only; all future product artifacts target ordinary repository paths. | PASS |
| VIII. Single-owner slices | Each slice has one stable owner lane, explicit edges, isolated work, and an integrator handoff. | PASS |
| Documentation freshness | Every slice reviews `README.md`, updates owned docs, hands exact shared claim deltas to 110, and must pass a post-convergence reviewer gate. | PASS |
| Security boundary | Transport-authenticated identity and host-owned capabilities govern privileged execution; room text and model judgment carry no authority. | PASS |

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

Wave 0 is not complete for this delivery target until accepted slice `010`
amendment A3 adds `I-010F` to the effective dependency packet. No `020` or `030`
implementation starts before that exact A3 commit and packet are accepted by
the consumer.

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
| `110-v2-parity-cutover` | `v2-integrator` | `010`–`100` | final cutover acceptance and verification |

`020` and `030` may run in parallel after `010`. `040` and `050` may overlap
only after their listed dependencies. The four surface lanes in Wave 3 may run
in parallel in separate worktrees. `100` audits landed slice handoffs; it does
not silently co-own their implementations. `110` is the only final sink.

## Interface Registry

Interface names and versions below are canonical planning identities. Slice
`010` creates their machine-readable forms under `schemas/v2/` during
authorized implementation.
No control-plane file is a product contract.

`I-010F`, `I-040B`, and `I-040C` are completion-target interfaces, not accepted
or implemented seams on this baseline. `I-010F` requires an accepted slice-010
amendment before any dependent work; `I-040B` and `I-040C` are then delivered
by slice `040`.

| ID | Interface | Owning slice | Named consumers / purpose | Planned ordinary home |
|---|---|---|---|---|
| `I-010A` | `AttentionRequestV2@1` | `010` | `020`, `030`, `050`–`110` | `schemas/v2/attention-request.schema.json` |
| `I-010B` | `AttentionDecisionV2@2` | `010` | `030`, `040`, `060`–`110`; `status: ok` carries `SUPPRESS`, `WAKE(advice)`, or `DEFER`; trusted `status: bypass` carries only `preattention-disabled`; `ERROR` remains separate | `schemas/v2/attention-decision.schema.json` |
| `I-010C` | `ParticipantWakeV2@1` | `010` | `040`, `060`–`110`; includes `PREATTENTION_BYPASS` without classifier/effective disposition | `schemas/v2/participant-wake.schema.json` |
| `I-010D` | `ContextContinuationV2@1` | `010` | `020`, `040`, `050`–`110`; host-only handle/binding plus request/page forms; classifier sees coverage/capability booleans only | `schemas/v2/context-continuation.schema.json` |
| `I-010E` | `AttentionReceiptV2@2` | `010` | `020`–`110`; immutable request-correlated observation, attention, participant-host, and transport stage union; each owner appends only its own off-surface record | `schemas/v2/attention-receipt.schema.json` |
| `I-010F` | `PrivilegedActionAuthorizationV2@1` | `010` | `040`, `060`–`110`; exact action ID/digest, capability, origin event, bounded scope, derived requester, `ALLOW`/`DENY`/`APPROVAL_REQUIRED`, reason, policy provenance, and host-only digest-bound approval challenge; no bearer grant reaches the participant | `schemas/v2/privileged-action-authorization.schema.json` |
| `I-020A` | `ObservationProviderV2@1` | `020` | `040`–`110`; native events to bounded `I-010A` plus continuation and factual current snapshot/high-water facts; no active-turn or pending-work scheduler | `src/nunchi/observation.py` |
| `I-030A` | `AttentionEngineV2@1` | `030` | `040`, `060`–`110`; callable core + CLI implementing `I-010A/B/E`, zero-call trusted bypass, classifier-safe projection, and the dual-valve transition | `src/nunchi/core.py`, `src/nunchi/cli.py` |
| `I-040A` | `ParticipantTurnHostV2@1` | `040` | `060`–`110`; refresh before invocation, wake, expansion, direct act-or-silence, no send reclassification | `src/nunchi/participant.py` |
| `I-040B` | `PrivilegedActionGuardV2@1` | `040` | `060`–`110`; resolve origin event to transport-attested actor, recheck trusted capability policy at execution, emit one-use `I-010F` decision, and execute only an exact allowed action | `src/nunchi/authorization.py` |
| `I-040C` | `ConversationOpportunitySchedulerV2@1` | `040` | `060`–`110`; per participant/room one active attention-or-participant turn plus one replaceable newest pending anchor, requesting a fresh `I-020A` snapshot on completion and discarding pending work on restart | `src/nunchi/scheduling.py` |
| `I-050A` | `DiscordEventSourceV2@1` | `050` | `070`, `080`, `100`, `110`; Discord native observation and continuity | `src/nunchi/mcp_discord/` |

Public schemas MUST reject reply prose, inferred social-state fields, alias-based
self identity, requester identities supplied by room/model text, reusable
authorization tokens, and any successful transition outside the selected
response and authorization matrices. A change to `I-010*` belongs to
`v2-contract-owner`; a consumer proposes and waits for a versioned successor
handoff rather than forking or silently mutating an inherited accepted packet.

## Integration Strategy

**Integration order**: accepted amendment A3 adds `I-010F` to slice `010`'s
effective contract packet first; observation and core attention land only after
independently accepting that exact commit and packet; participant wake and
shared Discord transport land next; harness/adapter lanes consume those
handoffs; security/provenance audits exact candidate commits; `v2-integrator`
assembles all accepted commits, runs parity, replaces truthful docs, and performs
one atomic V2 cutover.

**Worktree/branch**: each active slice lane uses `.worktrees/v2-<slice>/` and branch
`v2/<slice>`. Shared assembly uses `.worktrees/v2-integration/` and
`integration/v2`. Main remains V1 until the final accepted cutover.

**Handoff to**: foundation owners hand to every named dependent and
`v2-integrator`; surface owners hand to `v2-security-owner` and
`v2-integrator`; assurance hands its blocking report to `v2-integrator`.

**Acceptance ownership**: `v2-integrator` is the slice-level acceptance owner
for `010`–`100`; Zoe is the acceptance owner for `110`. Slice-level acceptance
does not stand in for a named consumer's acceptance. Before a dependent becomes
`READY`, its assigned owner records acceptance of every exact upstream commit,
interface version, and packet that dependency supplies.

**Conflict ownership**: `010` alone owns `schemas/v2/`; each implementation lane
owns only the files named in its plan; `110` alone owns cross-surface fixtures,
cutover choreography, public current-state documentation, and the final
integration conflict resolution. A needed shared-file edit is requested from
its owner and handed back as a commit.

**Atomicity**: lane branches may be green independently, but no surface is
called migrated and no partial V2 state lands on main. The integration branch
must contain all in-tree consumers on one contract before acceptance.

### Product decisions locked by this refresh

1. **No per-message response queue.** An accepted event is an observation, not
   a job. Each participant/room has at most one active attention/participant
   turn and one replaceable newest pending anchor. Intervening events remain
   factual context. Restart/backfill never replays wake work.
2. **Fresh stochastic judgment.** When idle, Nunchi does not wait for
   hypothetical future messages. When busy work completes, one fresh snapshot
   is assembled around the newest pending anchor and current room tail. No age,
   reply, mention, or apparent-resolution heuristic deterministically decides
   that the moment has passed.
3. **Trigger is not an obligation.** Attention and participant prompts identify
   the trigger only as an anchor and require judgment over the current room.
   Participant silence is valid when later context supersedes the moment.
4. **Honest pre-snapshot failure.** Unsupported, duplicate, or unroutable
   deliveries remain transport audits. If a canonical event exists but snapshot
   assembly fails, the host makes one bounded current-history recovery attempt.
   `ERROR_FALLBACK` requires the recovered valid snapshot; otherwise the host
   raises an operational failure and fabricates neither social suppression nor
   a participant action.
5. **One shared operator-policy boundary.** Core APIs accept validated typed
   policy. Each host loads it through the shared loader from trusted operator
   configuration; room input cannot select bypass, providers, models, endpoints,
   credentials, identity, budgets, capabilities, or failure behavior.
6. **Authorization is execution safety, not social judgment.** A participant may
   propose a capability and origin event. `I-040B` derives the requester from
   the retained canonical event, checks exact actor/capability/scope/revocation/
   expiry/approval against host policy immediately before execution, and binds
   `ALLOW` to one action digest. Missing or ambiguous authority returns `DENY`
   or `APPROVAL_REQUIRED`, never a model-decided allow.
7. **Approval is the safe default.** Mutating, destructive, external-effect,
   secret-bearing, and account/configuration capabilities require a host-only
   authenticated approval bound to the exact action digest unless trusted
   operator policy explicitly grants that actor direct execution for the exact
   capability and scope. Ordinary text, reactions, quotes, and copied approvals
   never satisfy the challenge; policy and digest are rechecked before one-use
   execution.
8. **Approval is completable without becoming a queue.** The host retains at
   most a bounded set of exact approval-bound proposals in expiring process
   memory and exposes them only to an authenticated operator surface. The full
   decision and participant-host receipt persist before an effect. Unknown
   persistence, restart, expiry, revocation, replay, or capacity exhaustion
   yields zero execution; restart never restores a pending proposal from room
   history.
9. **Boundary is explicit.** Nunchi enforces its own controls and the privileged
   seams implemented by supported integrations. A third-party tool path that
   bypasses `I-040B` is not claimed safe and blocks privileged-action support on
   that surface.

### Outcome-driven integration motion

- Treat accepted schemas, component candidates, branches, and evidence as
  inherited material. Preserve product decisions, but issue versioned
  successors where inherited interfaces cannot express freshness or action
  authorization. Never retain a hidden V1 or locally divergent path merely to
  preserve a packet's status.
- Deliver and accept `I-010F` through
  `evidence/v2/contract/amendment-A3-privileged-action-authorization.md`, based
  on exact effective predecessor
  `26a6b531fa146ba1f1f5fcd1c4d191041b141301`, before any `020` or later
  implementation. `020` owns bounded current
  observations and high-water facts; `040` owns `I-040C` coalesced scheduling,
  refresh-at-invocation, and the action guard; transports own authenticated
  identity/provenance; each platform packet maps its native config and tool
  seams to the shared contracts.
- The accountable integrator assembles all components continuously and rejects
  local success that fails the whole-room behavior, security boundary,
  installation, or documentation contract. Hermes and Claude Code return
  tested platform packets; Codex and reference adapters are integrated in the
  main implementation.
- Freeze one installable candidate only after deterministic suites, replay,
  repeated provider trials with classifier/effective distributions and flicker,
  separate post-hoc social review, live delayed-room scenes, restart continuity,
  authorization attacks, and installed-runtime provenance pass. Repeated social
  evidence may enforce narrow false-suppression constraints but never becomes a
  deterministic runtime oracle or send-time gate. Independent cross-family
  reviewers receive the same frozen commit and evidence. Any blocker produces a
  successor commit; that exact successor is reviewed again before atomic cutover.

**Rework**: A rejected handoff never erases an attempt. The designated recorder
appends `REJECTED` for the exact candidate; the slice owner returns to `ACTIVE`
and starts a new bound run because the prior run completed. Convergence-added
tasks also keep the slice `ACTIVE` and require a new bound run with the original
activation. Only paused post-convergence fixes with an unchanged task graph
resume their run. Later candidate/handoff attempts append. Integration checks
reject rewritten history, a resumed completed run, acceptance of a superseded
attempt, or downstream activation citing an unaccepted retry.

**Accepted amendments**: an `ACCEPTED` slice uses workflow version `2.6.0` in
accepted-amendment mode. It remains `ACCEPTED`; terminal activation, candidate,
handoff, acceptance, and earlier amendment records stay immutable. One
append-only amendment record fixes the stable owner lane, valid current
participant/assignment, ID/interface/versions, exact effective predecessor
commit and packet, ordinary scope, task manifest, evidence, documentation,
limitations, candidate, and packet. The integrator appends the decision there.
Rejection preserves the prior binding and starts a new run. Acceptance alone
appends one chained record to `slice-amendments.md`. A1/A2 retain their
historical accepted schema; this complete schema governs A3 onward.

If an accepted successor changes a dependency after consumer activation, the
consumer preserves its immutable historical records but cannot use the affected
candidate until its owner appends a compatibility re-attestation tied to the
exact successor commit and packet. A failing re-attestation replaces the
candidate rather than carrying it forward.

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
| `S17` Live-conversation freshness | A burst during a slow turn creates at most one later attention opportunity; intermediate events remain context, the newest pending event anchors a fresh snapshot, later resolution is visible, and restart/backfill never replays a wake backlog. | `020`, `040`, `050`–`110` | `evidence/v2/parity/s17-live-freshness/` |
| `S18` Provenance-bound privileged action | Exact origin event and transport actor bind a capability check at execution; aliases, quotes, replies, forged policy, unrelated/old authorized-user events, stale grants, cross-room replay, revoked/expired grants, copied/ordinary-text approvals, action mutation, unknown audit persistence, and pending-capacity exhaustion cannot authorize; high-impact actions default to an inspectable, expiring, exact digest-bound authenticated approval unless explicitly preauthorized, and pending approval is never restored after restart. | `010`, `020`, `040`–`110` | `evidence/v2/security/s18-action-authorization/`, `evidence/v2/parity/s18-action-authorization/` |

Every scene needs deterministic mechanics tests where deterministic facts are at
issue. Social-quality and cross-surface claims additionally need committed
replay and/or live evidence; unit tests alone cannot close them.

`S14` is executed as a fixed ladder: Hermes-only; Hermes + Claude Code; Hermes
+ Codex; Hermes + Claude Code + Codex; multi-human Discord; and multi-human
Telegram through Hermes. Normative lifecycle failures block cutover. Only facts
that a platform genuinely cannot expose may be recorded as limitations.
Admission-style meta-answers are graded after the participant turn as acceptance
failures; they do not justify a new runtime semantic send filter. The live
ladder injects delays and intervening resolution for `S17`, then exercises
authorized, unauthorized, approval-required, revoked, quoted-authority, and
cross-room cases for `S18`.

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
src/nunchi/authorization.py    # shared privileged-action guard
src/nunchi/scheduling.py       # shared per-participant/room opportunity scheduler
src/nunchi/mcp_discord/        # shared Discord event source
src/nunchi/adapters/           # standalone adapter bindings
integrations/hermes/           # Hermes binding
integrations/claude-code/      # Claude Code binding
src/nunchi/integrations/       # shared subprocess, Codex, and MCP transport bindings
tests/v2/                      # deterministic contract/integration/governance checks
evals/v2/                      # reusable replay corpora and runners
evidence/v2/                   # immutable run records and provenance
docs/                          # truthful product/integration/security/evaluation docs
```

## Ordinary Repository Targets

| Artifact class | Implementation target path(s) | Owning slice(s) |
|---|---|---|
| Product implementation | `src/nunchi/`, `integrations/` | `020`–`090` |
| Machine-readable contracts | `schemas/v2/` | `010` |
| Deterministic tests | `tests/v2/` | implementing slice; parity ownership in `110` |
| Evaluation runners/corpora | `evals/v2/` | `030`, `060`–`090`; parity ownership in `110` |
| Evidence | `evidence/v2/` | each slice for its run records; final index in `110` |
| Product and integration docs | `docs/` | implementing slice drafts; final truthful state in `110` |
| Security and authorization docs | `docs/security/` and `SECURITY.md` | implementation boundaries in `040`/surfaces; blocking assurance in `100`; final wording in `110` |
| Package identity, install, upgrade, restart, and rollback | `pyproject.toml`, packaging metadata, `docs/INSTALL.md`, `docs/operators/v2.md`, and exact installed-runtime evidence | assembled and proven in `110`; security/provenance audit in `100` |

## Program Documentation Freshness

Every implementing slice reviews `README.md` and its affected ordinary docs.
Known files are named exactly; generic directory scope is invalid. Slice task
progress stays dormant until Zoe's external grant is recorded at
`evidence/governance/v2-implementation-authorization.md` as one complete record
enumerating exactly slices `010` through `110`; the record documents but cannot
grant authority, and each bound slice still passes readiness independently.
Slices `010`–`100` use `UPDATE` for owned component guides and an exact
`HANDOFF` to `v2-integrator` for global current-state claim deltas. Slice `110`
must use `UPDATE` for `README.md` and all affected cross-surface docs; because
the atomic cutover changes current behavior, neither `NO_IMPACT` nor `HANDOFF`
is valid for that final global wording. The accepted candidate and atomic merge
remain truthful that exact-main verification and final current-state wording
are pending. Exact-main checks and final docs validation land together in one
docs/evidence-only follow-up; only then may the program become
`CUTOVER_VERIFIED` or docs call V2 current.

Each slice's ordinary handoff evidence records exact reviewed paths,
dispositions, validation results, reviewer, and—where applicable—the precise
delta and accepting owner. Planning checkboxes do not prove freshness. The full
workflow's post-convergence documentation gate reviews the exact candidate
before owner handoff.

The final documentation set MUST explain the live-conversation scheduler in
plain language and diagrams, define exact actor/capability/origin enforcement,
state which privileged seams each surface actually guards, and distinguish
Nunchi's guarantees from participant or third-party tool risks. At minimum the
cutover candidate updates `docs/architecture/v2-selected-design.md`,
`docs/security/v2.md`, `docs/operators/v2.md`, `docs/INSTALL.md`, each affected
installed-surface guide, and `README.md`; unsupported privileged-tool paths are
named as limitations rather than implied safe. The same committed set must
document and prove clean install, V1-to-V2 upgrade, restart continuity,
rollback, package/version identity, and removal of all hidden V1 paths without
depending on Vault access, conversation history, private session state, or
contributor-local files. These are the repository's
coherent ordinary-path surfaces: new parallel threat-model or operational-safety
documents are created only when they contain a genuinely separate maintained
contract, not to satisfy a stale filename in this plan.

## Lifecycle Evidence Contract

Within each slice's declared ordinary evidence directory, stable lifecycle files
use exactly these names and mutation contracts:

| Record | State established | Required subject |
|---|---|---|
| `slice-activation.md` | `READY` before the assigned participant declares `ACTIVE` | one immutable record of complete program authority, assigned participant/source, canonical accepted dependency IDs as they existed when this record was committed, ordered `slice=full-sha` Dependency commits, matching `slice=consumer-owned-evidence-file` Dependency acceptance references, analysis, worktree, starting commit, interfaces, scenes, evidence, docs scope, exact `Initial task IDs`, and normalized `Initial tasks SHA256`; later amendments use separate consumer acceptance and never rewrite activation; all three dependency fields are `none` for `010` |
| `slice-candidate.md` | `CONVERGED` | append-only stream whose latest attempt names the exact implementation candidate, its exact task IDs and normalized `Tasks SHA256`, `Tasks complete: YES`, and agreement among implementation, tests/evaluations, evidence, limitations, task state, and docs disposition; an exact-candidate review task may be open in the reviewed commit only when the later record-introduction commit preserves the same task IDs and shows every ID literally resolved |
| `slice-handoff.md` | `HANDOFF_READY`, or return to `ACTIVE` after rejection | append-only stream of exact candidate packets, named recipients, reviewer, reproduction commands, documentation-freshness result, and attributable `REJECTED` decisions |
| `slice-acceptance.md` | `ACCEPTED` | one immutable record of the exact accepted commit/packet and named slice-level acceptance owner |
| `amendment-<id>-<scope>.md` | bounded successor attempt while the slice remains `ACCEPTED` | one append-only record with fixed effective predecessor/scope/task manifest and later exact candidate, proof, docs, packet, and integrator decision; full schema mandatory from A3 onward |
| `slice-amendments.md` | effective dependency chain | append-only accepted-amendment summaries chaining exact predecessor to successor commit and exact amendment packet |

The assigned participant for a slice writes that slice's declarations and
immutable activation record, then appends candidate and handoff attempts after
the corresponding workflow gates. The assigned `v2-integrator` is the
designated recorder for every slice decision: on acceptance it writes immutable
`slice-acceptance.md`, and on rejection it appends a `REJECTED` decision to
`slice-handoff.md`, always with `Recorded by: v2-integrator`. For `010`–`100`
the integrator is also the acceptance owner; for `110`, Zoe remains the decision
owner and `Accepted by`/`Rejected by`. The source owner returns the slice
declaration to `ACTIVE` after rejection. Repair in the required new bound run
appends a new candidate and handoff attempt—no earlier entry is deleted or
rewritten. Each dependent recipient
separately writes its own upstream-acceptance file under the consumer evidence
directory. That file includes the upstream ID in its name and attests consumer,
upstream, matching effective commit, accepting participant/date, exact terminal
or amendment packet record, and durable decision. If that binding changes after
activation, the same consumer evidence stream appends a compatibility
re-attestation with the successor commit/packet, affected candidate,
verification, and `PASS` or `INCOMPATIBLE`; activation is never rewritten.
Slice `110` additionally requires every upstream slice to be
`ACCEPTED`. The assigned
`v2-program-owner` coordinates and verifies those records but writes only the
umbrella declarations and program-state transitions. The sole cross-slice
mechanical exception is synchronization of the complete externally granted
program-authority fact; it assigns no participant and changes no slice state.

The activation directories are `evidence/v2/contract/`,
`evidence/v2/observation/`, `evidence/v2/attention/`,
`evidence/v2/participant/`, `evidence/v2/discord-transport/`,
`evidence/v2/hermes/`, `evidence/v2/claude-code/`, `evidence/v2/codex/`,
`evidence/v2/adapters/`, `evidence/v2/security/`, and
`evidence/v2/parity/`. The program tail adjacent to slice `110` requires the
assigned integrator to copy Zoe's decision into slice acceptance/rejection
evidence and, on acceptance, the assigned program owner to copy that decision
only into `evidence/v2/parity/cutover-acceptance.md` with
`Recorded by: v2-program-owner`. The assigned integrator records the exact
merged-main verification and final docs validation in
`evidence/v2/parity/post-merge-verification.md`. The records substantiate state
declared in the umbrella and bound slice; collectively they are not a mutable
registry.

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
9. clean-install, upgrade, restart, rollback, and retired-V1-path results where
   the slice owns them; and
10. known limitations, residual risks, and any rejected claim.

An incomplete packet is not accepted. Reviewers challenge the packet but do not
silently take ownership. For slices `010`–`100`, `v2-integrator` records
slice-level acceptance or appends a `REJECTED` decision and sends the packet
back to the named owner lane. Rejection returns the declaration to `ACTIVE` and
requires a new bound delivery run; all later candidate/handoff attempts append
to the existing streams. Every
declared downstream recipient records its own acceptance separately, and the
source slice's `ACCEPTED` state does not imply those recipient records exist.
Each dependent's activation evidence uses ordered full-SHA and matching
consumer-owned acceptance-reference mappings for all required upstream packets.
An upstream successor blocks use of an affected dependent candidate until its
append-only compatibility re-attestation passes against the exact new effective
commit and packet; incompatibility requires replacement and never rewrites
historical acceptance.
For slice `110`, `v2-integrator` prepares the packet
and moves it through `CONVERGED` and `HANDOFF_READY`; only Zoe may decide on the
exact atomic candidate, and the assigned integrator records that decision and
then moves the slice declaration to `ACCEPTED` or back to `ACTIVE`.

The 2026-07-11 reset baseline in this plan is historical. Live program state,
slice state, and assigned occupants derive from the umbrella and exact
bound-slice declarations plus immutable ordinary-path activation/acceptance
records and append-only candidate/handoff attempt streams. This plan contains
no central mutable state or assignment registry.

## Complexity Tracking

None. No constitutional exception is authorized.
