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

## Decision 3: Stable role-based owner lanes with explicit assignment

**Decision**: Each slice has a canonical `v2-*-owner` lane. One externally
assigned participant occupies that lane, and both the participant and durable
assignment source are recorded in the slice declaration and immutable
ordinary-path activation evidence. Accountability follows the lane through an
explicit handoff.

**Rationale**: Runtime identities may change between sessions, while a stable
lane keeps ownership and integration edges unambiguous.

**Alternatives considered**: assign current room participant names in the
planning baseline (couples planning to availability); shared ownership
(recreates silent co-owning); a central assignment registry (creates a second,
mutable source of truth).

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
delete adapters while establishing the planning baseline (product mutation
outside that scope).

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

## Decision 9: Program progress, implementation authority, and slice progress are separate

**Decision**: Program progress uses `PLANNING -> READY -> DELIVERY ->
INTEGRATION -> CUTOVER_ACCEPTED -> CUTOVER_VERIFIED`. External implementation
authority is independently `NOT_GRANTED | GRANTED`. Every slice uses `PLANNED
-> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY -> ACCEPTED`. The dated
2026-07-11 reset planning baseline is program `READY`, authority `NOT_GRANTED`,
and all slices `PLANNED` and dormant. Live facts derive from the umbrella and
exact bound-slice declarations plus immutable activation/acceptance evidence
and append-only candidate/handoff attempt streams, not from a mutable
program-status table.

**Rationale**: A repository can be fully planned without having permission to
implement, and one authorized slice can still be unready because its owner,
dependencies, analysis, or worktree are missing. Conflating those facts makes
external participants treat session-level orchestration as repository state.

**Alternatives considered**: numbered session goals (not durable or portable
between participants); one boolean program status (cannot represent slice
readiness); checked task boxes as authority (planning artifacts cannot grant
external permission).

## Decision 10: Existing slices are bound explicitly and activated by immutable evidence

**Decision**: A participant selects one existing slice only through
`python3 scripts/run_slice_workflow.py run <nunchi-plan|speckit>
specs/<exact-slice>`. A paused unchanged-task run resumes only by run ID; a
completed-handoff rejection or convergence-added task starts a new bound run.
The runner owns the internal
environment binding and preflight. Its `slice-activation.md` records the one
valid complete program authorization record, independent slice readiness,
assigned participant and source, accepted upstream commits, analysis,
worktree, interfaces, evidence obligations, and docs scope before the slice
becomes `READY` or `ACTIVE`. Each exact activation path is declared by its
slice; no central mutable status registry is introduced.

**Rationale**: `.specify/feature.json` names the umbrella planning program and
is unsafe as an implicit delivery target. Exact binding prevents an external
participant from replacing a planned slice or implementing the umbrella while
immutable evidence makes readiness reviewable without becoming runtime state.

**Alternatives considered**: rely on the repository default feature (can bind
the umbrella accidentally); create a new feature for every delivery session
(fragments the selected slice); maintain a shared mutable registry (adds drift
and resembles the social-state mechanisms the product explicitly rejects).

## Decision 11: Slice acceptance and downstream consumption are separate

**Decision**: `v2-integrator` is the slice-level acceptance owner for slices
`010`–`100`; Zoe is the acceptance owner for slice `110`. Every declared
downstream owner also records its own acceptance of the exact upstream commit,
interfaces, and packet before its dependent slice becomes `READY`. A source
slice's `ACCEPTED` state never implies that every consumer has accepted unless
those per-recipient records exist.

**Rationale**: One source-level milestone is useful for program flow, but it
cannot truthfully attest another owner's consumption decision. Separate
recipient acceptance makes dependency readiness reviewable without turning a
central status table into a mutable service queue.

**Record shape**: The consumer activation lists canonical dependency IDs,
ordered `slice=full-sha` Dependency commits, and matching ordered
`slice=consumer-owned-evidence-file` Dependency acceptance references. Each
referenced file names consumer/upstream, matching commit, accepting
participant/date, exact packet record, and durable decision. Slice `010` uses
`none`; slice `110` accepts only terminally `ACCEPTED` upstream slices.

**Alternatives considered**: treat integrator acceptance as acceptance by all
consumers (false cross-owner attestation); wait for every possible consumer
before the source can be accepted (unnecessarily couples independent delivery);
track consumer status in an umbrella registry (duplicates evidence and drifts).

## Decision 12: Stable per-slice files preserve every delivery attempt

**Decision**: Every slice uses `slice-activation.md`, `slice-candidate.md`,
`slice-handoff.md`, and `slice-acceptance.md` in its declared ordinary evidence
directory. Activation and acceptance are immutable single-transition records.
Candidate and handoff files are append-only attempt streams: each retry appends
a new candidate and packet, while rejection appends `REJECTED`, exact candidate,
acceptance owner, ISO date, and durable decision reference to the handoff stream
and returns the slice declaration to `ACTIVE`. A completed-handoff rejection or
convergence-added task starts a new bound run while retaining activation; only
a paused post-convergence fix with an unchanged task graph resumes its run. No
prior attempt is deleted or rewritten. The program tail adjacent to slice `110` additionally uses
`cutover-acceptance.md` and `post-merge-verification.md` under
`evidence/v2/parity/`.

**Rationale**: Stable, local names make exact state discoverable, while
append-only attempts make rejection and rework truthful without a mutable
status ledger or lost review history.

**Alternatives considered**: infer state from task checkboxes (not evidence);
rewrite a rejected candidate or handoff in place (destroys audit history); keep
one program status ledger (central drift and cross-owner attestation); use ad
hoc evidence names per participant (hard to discover and validate).
