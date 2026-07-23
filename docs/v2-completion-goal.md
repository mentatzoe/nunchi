# Nunchi V2 completion goal

## Goal

Deliver Nunchi V2 as one coherent, secure, installable product that lets
multiple agents participate naturally in live shared conversations.

Nunchi spends attention through participant-shaped stochastic judgment, treats
messages as current observations rather than queued obligations, and permits
privileged actions only when trusted host controls verify the exact requester,
origin, capability, scope, and approval. Every supported surface implements one
portable contract. The product is complete only when deterministic,
stochastic, live, and adversarial evidence all support one self-contained,
independently reviewed release candidate whose installed behavior matches the
repository.

Existing source, specifications, branches, packets, and evidence are inherited
material. They may be reused when they satisfy this goal, but their existence
does not establish acceptance or constrain the integrator to preserve an
unsound implementation.

## End conditions

Nunchi V2 is complete only when all of the following are true:

1. **One product contract.** Identity, observation, attention, wake,
   continuation, scheduling, authorization, receipts, and errors have one
   portable V2 contract. Every retained entry point implements it; unsupported
   entry points are explicitly removed with their requirement disposition
   recorded. No hidden V1 or surface-local behavioral path remains.
2. **Live conversation, not queued work.** The product demonstrates
   `SUPPRESS`, `WAKE`, `DEFER`, trusted bypass, operational-error recovery, and
   direct participant act-or-silence. Per participant and room there is at most
   one active opportunity and one replaceable newest pending anchor.
   Intermediate events remain context; stale turns do not form a FIFO backlog
   or revive resolved conversation after restart.
3. **Deterministic authority boundaries.** Observation and every privileged
   action are bound to transport-attested identity and provenance. Capability,
   scope, policy, expiry, revocation, action digest, and any required
   authenticated approval are checked immediately before execution. Unknown,
   stale, forged, replayed, or mismatched authority fails closed without
   granting social meaning to deterministic code.
4. **Complete supported surface.** Core, CLI, shared transport, Codex, Hermes,
   Claude Code, Discord, and the agreed reference adapters are installed and
   exercised against the same contract. Support and exclusions are explicit;
   no requirement disappears merely because an implementation is difficult.
5. **Operationally usable.** A clean install, upgrade, restart, rollback, and
   mixed-agent room work from repository documentation alone. Restart
   continuity, replies, mentions, reactions, silence, failures, and recovery
   have bounded, inspectable behavior.
6. **Evidence matches the risks.** Deterministic tests prove contract and state
   semantics. Stochastic multi-model evaluations and replay test social
   judgment. Live mixed-room ladders prove installed cross-platform behavior.
   Adversarial checks cover identity, provenance, authorization, cancellation,
   races, capacity, restart, malformed inputs, and output-closure boundaries.
7. **The repository is self-contained.** A new contributor can understand,
   build, test, operate, review, and continue V2 without Aleph Vault,
   conversation history, or private session state. Historical Vault commits
   remain provenance for the selected decisions, not a runtime or contributor
   dependency.
8. **Dependencies are terminal before downstream work starts.** A downstream
   slice may begin implementation only after every declared upstream slice is
   accepted at an exact commit and its packet is accepted by that consumer.
   Any successor that changes an upstream contract invalidates affected
   downstream acceptance until compatibility is re-proved; incompatible work
   is replaced rather than preserved for sunk-cost reasons.
9. **One frozen candidate closes review.** The complete candidate is
   byte-frozen and receives independent cross-family review. A blocking finding
   produces a new exact successor, and that successor is reviewed again.
   Source review, installed-runtime verification, live evidence, lifecycle
   acceptance, and release are recorded as distinct facts.
10. **Cutover is atomic and truth remains exact.** All retained V2 surfaces cut
    over together. The resulting `main` commit is reverified, current-state
    documentation is validated against installed behavior, and only then is V2
    `CUTOVER_VERIFIED`. Release and promotion remain separate explicit
    decisions.

## Delivery constraints

- One accountable integrator owns the end-to-end outcome, dependency order,
  shared seams, integration, and final candidate.
- Platform owners may implement bounded packets only after their accepted
  dependencies are stable. Packet ownership does not transfer integration
  accountability.
- Reviews exist to find product defects. They must be tied to exact bytes and
  reproducible evidence, without synthetic approval choreography.
- Verification and documentation are product work, not a tail phase.
- Green tests cannot override a broken invariant, an unproven installed path,
  stale provenance, or a known lifecycle contradiction.

## Completion decision

Completion is a product claim, not the sum of checked tasks. It is made only
from the exact frozen candidate and the end conditions above. If any condition
is false or unproven, the program remains incomplete and the next action is the
smallest work that closes that product gap without weakening the goal.
