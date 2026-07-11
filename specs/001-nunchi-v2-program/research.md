# Planning Research: V2 Program Decomposition

This file records control-plane decomposition decisions only. It does not define
or contain product contracts.

## Decision 1: Contract-first dependency spine

**Decision**: Slice `010` owns the V2 interface family. Observation (`020`) and
core attention (`030`) may proceed in parallel after it; participant wake (`040`)
joins them before consumer integrations.

**Rationale**: Consumers can work independently only against one versioned
contract. Observation collection and classifier execution are separate concerns
and do not need to block each other after the contract is fixed.

**Alternatives considered**: one monolithic foundation slice (too much shared
context and ownership); adapter-first evolution (repeats parity drift).

## Decision 2: Transport and harness integrations are separate lanes

**Decision**: Shared Discord-MCP transport is slice `050`; Hermes, Claude Code,
Codex, and standalone channel adapters are slices `060` through `090`.

**Rationale**: Transport attests native facts and continuity; harnesses own
participant invocation and no-send. Combining them would blur interfaces and
make Codex's shared transport a hidden dependency of unrelated surfaces.

**Alternatives considered**: one adapter mega-slice (ownership conflicts);
surface-by-surface contract forks (no parity).

## Decision 3: Stable role-based owner lanes

**Decision**: Each slice has a canonical `v2-*-owner` lane. A Goal 2 runtime or
human occupies that lane; accountability follows the lane through explicit
handoff.

**Rationale**: Runtime identities may change between sessions, while a stable
lane keeps ownership and integration edges unambiguous.

**Alternatives considered**: assign current room participant names before Goal 2
(couples planning to availability); shared ownership (recreates silent co-owning).

## Decision 4: Assurance is blocking, parity is the final sink

**Decision**: Security/provenance (`100`) audits every implementation lane and
blocks parity/cutover (`110`). Slice `110` alone owns final assembly and parity
evidence.

**Rationale**: Cross-cutting safety cannot be considered complete before the
surfaces exist, and no component owner should self-certify system parity.

**Alternatives considered**: embed all assurance in each slice (inconsistent
standards); let every slice merge independently to main (mixed V1/V2 state).

## Decision 5: All in-tree consumers migrate; release tier remains separate

**Decision**: Generic, Matrix, Telegram, and Discord channel adapters are in the
V2 cutover even if their future product/release tier remains open.

**Rationale**: Leaving an in-tree V1 consumer contradicts atomic cutover and
creates an ambiguous public surface. Migration scope and release promotion are
different decisions.

**Alternatives considered**: migrate only live-proven harnesses (mixed contract);
delete adapters during Goal 1 (product mutation outside scope).

## Decision 6: Common scene catalog, surface-specific evidence

**Decision**: The umbrella defines shared acceptance-scene IDs; slices bind them
to their available facts and ordinary evidence paths.

**Rationale**: One catalog makes parity comparable without pretending every API
exposes identical facts.

**Alternatives considered**: per-surface unrelated scenarios (not comparable);
one synthetic universal transcript (invents unavailable facts).

## Decision 7: Disabled preattention is an explicit non-model bypass

**Decision**: Trusted `preattention-disabled` configuration returns a tagged
bypass, invokes the participant with source `PREATTENTION_BYPASS`, and records
that the classifier was not invoked. It carries no classifier or effective
social disposition.

**Rationale**: Disabling Nunchi should restore the participant's ordinary turn,
not forge model WAKE/DEFER semantics or turn an operational configuration into
a social judgment.

**Alternatives considered**: fabricate WAKE (false model provenance); map to
DEFER (misstates uncertainty); route outside the shared lifecycle (parity fork).

## Decision 8: Receipt facts are immutable owner stages

**Decision**: I-010E is a union of request-correlated observation, attention,
participant-host, and transport stages. Each owner emits only its own immutable
record. Host-only continuation authority remains out of classifier input; the
model sees factual coverage and expansion-availability booleans only.

**Rationale**: A mutable “complete receipt” would create hidden shared state,
let early owners claim future facts, and blur whether unknown outcomes were
observed. Projection separation also prevents opaque host authority from
becoming prompt data.

**Alternatives considered**: one incrementally mutated record (cross-owner race
and false attestation); give continuation handles to the classifier (authority
leak); omit lifecycle correlation (unreviewable evidence).
