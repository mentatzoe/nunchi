<!--
Sync Impact Report
Version change: 1.0.0 -> 2.0.1
Major-bump rationale: replaces the V1 admission/move-vocabulary constitution
with the selected V2 pre-attention design and makes SpecKit a disposable,
control-plane-only execution spine.
Patch clarification: encodes the already-selected direct wake when preattention
is disabled, host-only continuation authority, and immutable singly attested
receipt stages after independent planning red-team review.
Modified principles:
- Admission, Not Composition -> Selected V2 Product Boundary
- Hard-Stop PASS Is Load-Bearing -> Human-Shaped Social Judgment
- CLI-First, Modular Core -> Truthful Identity and Observation
- Vertical, Independently Testable Slices -> Attention and Contribution Have Different Owners
- Test-First Contract and Fixture Discipline -> Atomic Contract and Cross-Surface Parity
- Adapter Tier Honesty and Consumer Boundaries -> Evidence Before Claims
- Context Truth and Room Inference -> SpecKit Is Control-Plane Only
- Documentation Is Product -> Single-Owner Slices and Deliberate Integration
Added sections:
- Authority and Repository Boundaries
- Goal and Workflow Gates
Removed sections:
- V1 Product Boundaries
- V1 SpecKit Workflow & Review Gates
- V1 Agent Execution Hygiene
Dependent artifacts:
- ✅ .specify/templates/plan-template.md (control-plane-only plan shape)
- ✅ .specify/templates/spec-template.md (source, owner, dependency, and boundary fields)
- ✅ .specify/templates/tasks-template.md (ordinary-path task targets and owner handoff)
- ✅ .specify/workflows/speckit/workflow.yml (full governed sequence + Goal 2 gate)
- ✅ .specify/workflows/nunchi-plan/workflow.yml (planning-only workflow)
- ✅ AGENTS.md and CLAUDE.md (authority order and runtime instructions)
- ✅ README.md (truthful V1/V2 state and development method)
- ✅ docs/governance/execution-spine.md (operator workflow and reinitialization)
- ✅ scripts/check_governance.py and tests/test_governance.py (mechanical enforcement)
Follow-up TODOs: none
-->

# Nunchi Constitution

## Core Principles

### I. Selected V2 Product Boundary

Nunchi MUST be the participant's delegated pre-attention for shared
conversation. The selected V2 gate-facing outcomes are `SUPPRESS`, `WAKE`, and
`DEFER`; operational `ERROR` is a separate path. Nunchi decides whether a room
event is worth waking the participant. It MUST NOT compose the participant's
reply, allocate the floor, coordinate speakers, or decide which social move the
participant eventually makes.

Trusted preattention-disabled configuration MUST bypass model judgment and wake
the participant directly. That host branch MUST remain distinguishable from a
model `WAKE`, `DEFER`, or operational `ERROR`; it MUST NOT fabricate a
classifier or effective social disposition.

The repository's current V1 `PASS / ACK / ASK / SPEAK` implementation remains
implementation truth until Goal 2 replaces it atomically. Goal 1 MUST NOT change
product behavior or claim that V2 is implemented.

Rationale: the product failed when attention admission and contribution shape
were treated as the same decision, and when target design was confused with
current code.

### II. Human-Shaped Social Judgment

Only an explicitly authorized, participant-shaped model judgment over truthful
facts MAY socially suppress a wake. Deterministic code MAY suppress or discard
only transport-proven non-events: exact duplicate delivery, an exact self event
that is retained but does not wake its author, or a payload from which no
authorized and routable native event can be constructed. Deterministic code
MUST NOT interpret mentions, replies, topology, apparent resolution, relevance,
or any other conversational meaning.

Uncertainty MUST widen attention through `WAKE` or `DEFER`; it MUST NOT be
converted into silence by a heuristic. Governed suppression MUST remain
inspectable, revocable, recoverable for later hearing, and separately
receipted. Later hearing does not restore a missed conversational moment, so
false suppression remains the highest-risk branch.

Rationale: algorithmic social gates produced the Claude/Station false-silence
failure. Nunchi exists to use model nuance, not to encode a brittle social
algorithm around it.

### III. Truthful Identity and Observation

Every V2 judgment MUST receive exact current-surface self binding separately
from loose names, roles, and aliases. Loose descriptors MAY support model
reasoning but MUST NOT establish authorship or self identity. Conversation input
MUST preserve ordered native events, stable actors, literal reply/mention/
reaction/membership relations when available, the trigger, and honest coverage
and gap facts.

Eager context MUST be bounded by explicit event and byte budgets. Older or
distant context MAY be exposed through participant- and room-bound continuation
where the host can provide it truthfully. The system MUST model observed and
referenced actors, not invent a complete participant roster or registry.

Opaque continuation handles, bindings, cursors, expiry values, and fetch
authority MUST remain host-only and MUST NOT enter classifier input. The model
MAY receive factual coverage and whether bounded expansion is available.

No component MAY maintain a handled/unhandled, addressed/unaddressed,
obligation, or speaker queue as social memory. Overlapping windows are
observations, not consumed work items. Operational receipts MUST remain
off-surface telemetry. Receipt records MUST be immutable and request-correlated;
observation, attention, participant-host, and transport owners may attest only
their own stage and MUST NOT mutate or fill another owner's facts.

Rationale: Nunchi needs enough structured perception to read the room without
turning a social conversation into a FIFO service queue or a context bomb.

### IV. Attention and Contribution Have Different Owners

The pre-attention model MUST answer only whether to spend a wake. After `WAKE`,
`DEFER`, trusted preattention bypass, or operational-error fallback, the harness
MUST deliver a normal participant turn containing the room event and compact
factual context. The participant then contributes through its normal message,
reaction, or tool path, or sends nothing.

The participant MUST NOT be asked to return an intermediate yes/no answer about
wanting to contribute. A transport send path MUST NOT run a second social
classifier or require per-trigger social permission state. Deterministic send
backstops MAY enforce operational safety without reinterpreting the room.

Rationale: judging admission twice caused valid wakes to be silenced at send
time. One attention judgment plus one ordinary participant turn preserves the
correct ownership boundary.

### V. Atomic Contract and Cross-Surface Parity

V2 is a breaking replacement of the request, response, and lifecycle contract.
Goal 2 MUST move the core, CLI, every in-tree adapter, and every in-tree agent
harness to one contract without a mixed-version repository or a V1 translation
bridge. The classifier-DEFER and margin-DEFER transition is independently
evidence-gated and MUST NOT be conflated with schema compatibility.

Equivalent platform facts MUST normalize to equivalent observations, attention
routing, and participant factual availability across Hermes, Claude Code,
Codex, Discord-MCP, and the standalone channel adapters. A platform MUST NOT
invent facts its API cannot supply; unavailable capability MUST be represented
honestly. Each surface MUST prove installed-runtime provenance and a live V2
probe before it is called migrated.

Rationale: local success without adapter and harness parity recreates the
failure class that triggered V2.

### VI. Evidence Before Claims

Contract changes MUST be defined by ordinary-path schemas and tests before
implementation is accepted. Offline tests MUST remain deterministic; stochastic
social correctness MUST be evaluated through committed replay corpora,
multi-model evidence where required, and live acceptance scenes. A green unit
suite proves mechanics, not social quality.

Every completion claim MUST cite a reproducible command and the committed test,
fixture, evaluation, or evidence record that supports it. Documentation MUST
distinguish current V1 behavior, selected V2 design, planned work, code-only
integration, bounded live evidence, and sustained operational evidence.
Release and promotion remain separate decisions.

Rationale: schemas and prose previously looked complete while the runnable
cross-surface lifecycle was not.

### VII. SpecKit Is Control-Plane Only (NON-NEGOTIABLE)

SpecKit-managed paths are disposable execution control plane. In this
repository they are `.specify/`, `specs/`, `.agents/skills/speckit-*`, and
`.claude/skills/speckit-*`. They MAY own only tool configuration, the
constitution, planning specifications, plans, planning research, requirement
quality checklists, task lists, ownership, dependencies, workflow definitions,
and ephemeral workflow state.

They MUST NEVER own or contain product implementation, machine-readable product
contracts or schemas, executable tests, evaluation runners or corpora, fixtures,
evidence, runtime/deployment assets, or product/user documentation. Those assets
MUST live in ordinary repository paths such as `src/`, `schemas/`, `tests/`,
`evals/`, `evidence/`, `integrations/`, `scripts/`, and `docs/`.

Build, test, evaluation, documentation, packaging, release, and runtime paths
MUST NOT depend on a SpecKit-managed path. Deleting and reinitializing all
SpecKit-managed paths MAY destroy planning state but MUST leave the product,
its tests, its evidence, and its documentation runnable and intelligible.
Repository checks MUST enforce this boundary.

Rationale: a planning tool must be replaceable without deleting or disabling
the product truth it organizes.

### VIII. Single-Owner Slices and Deliberate Integration

One umbrella V2 program MUST define independently executable slices. Every
slice MUST name exactly one accountable owner lane, its upstream dependencies,
interfaces it consumes and produces, ordinary-path implementation targets,
integration branch or handoff strategy, acceptance scenes, and evidence
requirements. Reviewers MAY challenge and red-team; they MUST NOT silently
co-own or mutate another slice's scope.

Non-trivial slice work MUST use an isolated worktree. Parallel slices MUST not
edit the same contract or integration file without an explicit handoff. Shared
contract changes land before dependent slices; harness integrations land before
the final parity slice. The final integrator owns cross-surface assembly and may
reject a locally green slice whose interface or evidence does not match the
program contract.

Rationale: explicit ownership and integration order preserve parallelism
without recreating the previous detached patchwork.

## Authority and Repository Boundaries

Authority is ordered as follows:

1. Zoe-selected Aleph Vault decisions and technical design, selected in PR 67
   at `bdd1ebb` and contract-clarified in PR 68 at `c834e8c`.
2. This constitution, which translates those decisions into repository
   invariants.
3. `AGENTS.md` and `CLAUDE.md`, which provide runtime-specific execution
   guidance without changing product decisions.
4. The active SpecKit umbrella and slice artifacts, which organize authorized
   work without redefining higher authority.

Ordinary-path source, schemas, tests, evaluations, evidence, and documentation
are authoritative for what is currently implemented and proven. A planning
artifact MUST NOT claim capability that those artifacts do not establish. When
the Vault design and current implementation differ, both MUST be stated:
selected target versus current behavior.

The canonical ordinary-path homes are:

- `src/` and `integrations/`: product and integration implementation;
- `schemas/`: machine-readable public and inter-component contracts;
- `tests/`: deterministic unit, contract, integration, and governance tests;
- `evals/`: evaluation runners and reusable corpora;
- `evidence/`: immutable or append-only run records and indexes;
- `docs/`: product, integration, security, evaluation, and governance docs;
- `scripts/`: repository tooling, including governance validation.

## Goal and Workflow Gates

The program has two separately authorized goals:

- **Goal 1 — execution spine**: pin and initialize SpecKit, relocate product
  artifacts, establish governance, define the umbrella and slices, and validate
  the baseline. Goal 1 MUST NOT implement V2 product behavior.
- **Goal 2 — end-to-end V2**: separately commissioned implementation, atomic
  cutover, integration, live deployment verification, and parity evidence.

Every implementation slice MUST pass this control-plane sequence:

```text
constitution -> specify -> clarify -> plan -> checklist -> tasks -> analyze ->
explicit Goal 2 authorization -> implement -> converge -> parity integration
```

The planning-only workflow MUST stop after analysis. The full workflow MUST have
an explicit authorization gate immediately before implementation. No workflow
MAY infer Goal 2 authorization from the existence of tasks or from completion of
Goal 1.

For Nunchi, `spec.md`, `plan.md`, `research.md`, `tasks.md`, and requirement
quality checklists are control-plane artifacts. The standard SpecKit
`data-model.md`, `contracts/`, and `quickstart.md` outputs are prohibited inside
managed paths; interface design, runnable validation guides, machine-readable
contracts, and user documentation MUST instead be created under their ordinary
repository homes during an authorized implementation goal. Plans MUST name
those target paths without embedding the product artifacts.

Before implementation, analysis MUST report zero CRITICAL or HIGH findings,
the accountable owner MUST be active, dependencies MUST be satisfied or
explicitly staged, and the slice's acceptance scenes and evidence locations
MUST be concrete. Before integration, the slice owner MUST hand off a commit,
verification commands, evidence references, and known limitations to the final
integrator.

## Governance

This constitution supersedes repository READMEs, issue text, agent prompts,
workflow defaults, and SpecKit templates when they conflict. It does not
supersede a later explicit Zoe decision; such a decision requires this file and
its dependent artifacts to be amended before conflicting work begins.

Amendments require:

- written rationale and project-owner authorization;
- semantic version bump and updated Sync Impact Report;
- review of templates, workflows, agent guidance, boundary checks, active
  program/slices, and ordinary documentation;
- proof that the full offline baseline remains green or an explicit approved
  migration exception.

Versioning policy:

- MAJOR for principle removal, product-boundary reversal, authority-order
  change, or backward-incompatible governance;
- MINOR for a new principle, required gate, or materially expanded obligation;
- PATCH for non-semantic clarification.

Compliance review is mandatory before product implementation, slice handoff,
integration, release, and any live-readiness claim. Any unexplained violation
blocks the affected work. Goal completion requires the repository governance
check and full existing test baseline to pass.

**Version**: 2.0.1 | **Ratified**: 2026-05-22 | **Last Amended**: 2026-07-11
