<!--
Sync Impact Report
Version change: 2.4.0 -> 2.5.0
Minor-bump rationale: adds a bounded, executable post-acceptance amendment path
that preserves terminal history, validates the current owner-lane occupant,
and prevents downstream work from starting against a superseded dependency.
Modified principles:
- Program and Slice Lifecycle Gates (accepted amendments and effective packets)
Dependent artifacts:
- ✅ Spec/plan/tasks/checklist templates (slice lifecycle metadata and gates)
- ✅ nunchi-plan and speckit workflows and installed skills (amendment mode)
- ✅ AGENTS.md, CLAUDE.md, README.md, and execution-spine guidance
- ✅ umbrella program and slice authority declarations
- ✅ governance checker and tests (terminal dependency and amendment enforcement)
- ✅ completion goal and inherited-state baseline
Follow-up TODOs:
- Deliver and accept I-010F through the slice-010 amendment path, then re-plan
  slice 040 to define I-040B, I-040C, S17, and S18 before activation; refresh
  downstream packets only after their dependencies accept.
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
implementation truth until the accepted V2 atomic cutover lands and is verified
on `main`. Planning and governance changes MUST NOT claim that V2 is
implemented.

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
The authorized V2 implementation program MUST move the core, CLI, every in-tree
adapter, and every in-tree agent harness to one contract without a mixed-version
repository or a V1 translation bridge. The classifier-DEFER and margin-DEFER
transition is independently evidence-gated and MUST NOT be conflated with
schema compatibility.

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

Every implementation slice MUST review `README.md` and every ordinary-path
document whose claims intersect its changed behavior, interfaces,
configuration, installation, supported surfaces, evidence grade, limitations,
security posture, or current/release state. Impacted documentation MUST be
updated and validated with the implementation before handoff. Documentation
review is part of implementation evidence, not optional polish.

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

Shared documentation follows the same single-owner rule. A slice that cannot
edit an integrator-owned document MUST hand off the exact required wording or
claim delta and name the accepting owner. It MUST NOT silently defer the work or
mislabel a known future change as having no documentation impact.

Rationale: explicit ownership and integration order preserve parallelism
without recreating the previous detached patchwork.

## Authority and Repository Boundaries

Authority is ordered as follows:

1. The repository-owned selected design at
   `docs/architecture/v2-selected-design.md` and portable contract reference at
   `docs/contracts/nunchi-v2.md`. They preserve the Zoe-selected decisions from
   Aleph Vault PR 67 (`bdd1ebb`) and PR 68 (`c834e8c`); those external commits
   are provenance, not a contributor or runtime dependency.
2. This constitution, which translates those decisions into repository
   invariants.
3. `AGENTS.md` and `CLAUDE.md`, which provide runtime-specific execution
   guidance without changing product decisions.
4. The active SpecKit umbrella and slice artifacts, which organize authorized
   work without redefining higher authority.

Ordinary-path source, schemas, tests, evaluations, evidence, and documentation
are authoritative for what is currently implemented and proven. A planning
artifact MUST NOT claim capability that those artifacts do not establish. When
the selected design and current implementation differ, both MUST be stated:
selected target versus current behavior.

The canonical ordinary-path homes are:

- `src/` and `integrations/`: product and integration implementation;
- `schemas/`: machine-readable public and inter-component contracts;
- `tests/`: deterministic unit, contract, integration, and governance tests;
- `evals/`: evaluation runners and reusable corpora;
- `evidence/`: immutable or append-only run records and indexes;
- `docs/`: product, integration, security, evaluation, and governance docs;
- `scripts/`: repository tooling, including governance validation.

## Program and Slice Lifecycle Gates

Program progress and implementation authority are separate facts. Program
progress uses:

```text
PLANNING -> READY -> DELIVERY -> INTEGRATION -> CUTOVER_ACCEPTED ->
CUTOVER_VERIFIED
```

Implementation authority is independently `NOT_GRANTED` or `GRANTED`.
Completing the planning baseline, creating tasks, changing a state label, or
creating evidence MUST NOT grant authority.

Zoe, or an assigner named by a durable Zoe delegation, MAY assign the
`v2-program-owner` and the occupant of a slice's accountable owner lane.
Declarations use `<participant identity>` —
`evidence/governance/assignments/<record>.md`. That non-symlink repository record
MUST contain exactly one `Assignee`, `Lane`, `Assigned by`, ISO `Assigned on`,
and durable `Authority reference`. When `Assigned by` is not Zoe, it MUST also
contain `Delegated by: Zoe` and a durable `Delegation reference`; transient
chat or session memory alone is invalid. Assignment MAY happen during
planning before implementation authority exists, but it neither grants that
authority nor activates a slice. Only the bound slice needs an occupant for its
readiness gate; work on one slice MUST NOT wait for unrelated slices to be
staffed. The `v2-integrator` is the one deliberate early exception: its
occupant MUST be assigned before the first `010`–`100` terminal-acceptance
decision, without activating slice `110`. The program owner coordinates program
facts and MUST NOT silently own or write another participant's slice lifecycle
evidence.

Each slice `010` through `110` uses:

```text
PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY -> ACCEPTED
```

- `PLANNED`: its control-plane artifacts agree; implementation remains dormant.
- `READY`: the one complete program authority record is valid and enumerates
  exactly slices `010` through `110`, one accountable occupant is assigned
  from a durable source, every declared upstream slice needed by this consumer
  is terminally `ACCEPTED` at an exact full commit and its packet is accepted
  by that consumer with a durable
  per-consumer acceptance reference, and analysis has zero CRITICAL/HIGH
  findings. Slice `110` additionally requires every slice `010` through `100`
  to be `ACCEPTED`. After those facts are accepted, the owner writes immutable
  slice activation evidence recording the exact worktree, interfaces, scenes,
  evidence targets, and documentation dispositions; that record plus matching
  declarations establishes `READY` before any move to `ACTIVE`.
- `ACTIVE`: that occupant is implementing only this slice in its isolated
  worktree.
- `CONVERGED`: every planned task is complete and the latest entry in the
  append-only candidate stream
  proves implementation, tests/evaluations, interfaces, and known limitations
  agree.
- `HANDOFF_READY`: documentation freshness has passed for the exact candidate
  and the latest entry in the append-only handoff stream records the complete
  packet.
- `ACCEPTED`: the designated slice-level acceptance owner accepts the exact
  commit and packet in immutable acceptance evidence. For slices `010` through
  `100` that owner is `v2-integrator`; for slice `110` it is Zoe. Each dependent
  separately records acceptance of the upstream handoffs it consumes before it
  may become `READY`; slice-level `ACCEPTED` does not fabricate those
  per-consumer facts. A rejection appends a `REJECTED` record to the existing
  handoff file, naming the rejected candidate, acceptance owner, ISO date, and
  durable decision reference, then returns the slice to `ACTIVE` under the same
  owner. A new candidate and handoff are appended as new attempts; no rejected
  attempt is deleted or rewritten. Because a handed-off run is complete, rework
  MUST start a new bound delivery run for that same slice and MUST NOT resume the
  completed run. If convergence appends tasks, the slice likewise remains
  `ACTIVE`, retains its original activation, and starts a new bound run. Only
  fixes requested by a paused post-convergence gate with an unchanged task graph
  MAY resume that run. Review never transfers ownership silently.

An `ACCEPTED` slice never moves backward merely because its owner must issue a
versioned successor. A bounded post-acceptance amendment uses the existing
`speckit` delivery workflow in amendment mode and obeys all of these rules:

- the stable owner lane remains accountable, while exactly one valid current
  occupant is named from a durable Zoe/delegate assignment in the amendment
  record; the historical activation occupant remains unchanged;
- the declared lifecycle state remains `ACCEPTED`, and its activation, terminal candidate,
  terminal handoff, terminal acceptance, and prior amendment records are
  immutable. Clearly labelled amendment sections MAY be appended to the
  existing spec, plan, and tasks; completed task history remains byte-for-byte
  unchanged;
- the amendment fixes one ID, interface, prior and new versions, current
  effective predecessor commit and packet, rationale, ordinary-path scope,
  task manifest, evidence, documentation dispositions, and limitations before
  implementation;
- the candidate MUST descend from the current effective predecessor, and its
  record and packet live in one append-only amendment file rather than the
  terminal candidate or handoff streams;
- the designated acceptance owner records `ACCEPTED` or `REJECTED` in that
  amendment file. Rejection leaves the prior effective commit and packet
  unchanged and requires a fresh bound run; and
- only acceptance permits one append to the canonical
  `slice-amendments.md` ledger. That append changes the effective dependency
  commit and packet for new consumers without changing historical slice
  acceptance. Every affected consumer MUST stop using its prior candidate until
  compatibility with the exact successor is independently re-proved; an
  incompatible candidate is replaced.

If an accepted amendment lands after a consumer was activated, the immutable
activation continues to record the dependency that was true at activation
time. The consumer MUST append a compatibility re-attestation to its existing
dependency-acceptance file before using that candidate again. The new record
names the prior and exact new effective commits, exact amendment packet,
affected candidate commit, concrete compatibility evidence, and `PASS` or
`REPLACE`; only `PASS` permits continued use. A consumer activated after the
amendment MUST bind the effective successor directly and cannot use a
re-attestation to excuse a stale initial binding.

No central mutable slice-status registry is permitted. Current state MUST be
derived from the slice's declared control-plane state, immutable activation
and acceptance records, and append-only candidate and handoff attempt streams.
Slice `110` specializes the tail:
after it accepts slices `010` through `100`, it assembles one candidate; Zoe's
explicit decision is copied into slice acceptance evidence by the assigned
`v2-integrator`; on acceptance, the assigned `v2-program-owner` copies it into
`evidence/v2/parity/cutover-acceptance.md`, establishing `CUTOVER_ACCEPTED` and
permitting one atomic merge. The merged candidate's documentation MUST remain
truthful that V2 is `CUTOVER_ACCEPTED` with exact-main verification pending; it
MUST NOT describe V2 as the verified current product. Only verification of the
resulting main commit plus validation of the final current-state documentation
in a docs/evidence-only follow-up at
`evidence/v2/parity/post-merge-verification.md` establishes
`CUTOVER_VERIFIED`. Neither decision authorizes release or promotion.

Lifecycle evidence uses one file per transition, never a mutable aggregate:

- `slice-activation.md` names the slice, `READY` status, participant and durable
  assignment reference, authority record, canonical accepted dependency IDs,
  exact ordered `Dependency commits` as `slice=full-sha`, and matching ordered
  `Dependency acceptance references` as
  `slice=repo-relative-evidence-reference`. Each reference MUST be a
  consumer-owned evidence file whose name includes the upstream ID and whose
  metadata names consumer slice, upstream slice, matching candidate commit,
  accepting participant, ISO date, exact upstream packet record, and durable
  decision reference, zero-blocker analysis result, branch/worktree and starting
  commit, interfaces,
  scenes, evidence targets, documentation scope, the exact `Initial task IDs`,
  and their normalized `Initial tasks SHA256`;
- `slice-candidate.md` names the slice, `CONVERGED` status, exact candidate
  commit, exact `Completed task IDs`, matching normalized `Tasks SHA256`,
  `Tasks complete: YES`, verification commands/results, interface versions,
  evidence paths, and known limitations;
- `slice-handoff.md` appends `HANDOFF_READY` attempts naming candidate commit,
  acceptance owner, documentation-freshness result, and exact existing packet
  files; a rejection appends the corresponding `REJECTED` decision with
  `Recorded by: v2-integrator`; and
- `slice-acceptance.md` names the slice, `ACCEPTED` status, candidate commit,
  accepting owner, ISO acceptance date, durable decision reference, and
  `Recorded by: v2-integrator`; and
- `amendment-<id>-<scope>.md` is one append-only amendment record containing
  the stable owner lane, valid current occupant and assignment reference,
  amendment ID/interface/versions, predecessor commit and packet, fixed scope
  and task manifest, candidate, verification, evidence, documentation
  dispositions, limitations, `HANDOFF_READY` packet, and the integrator's
  `ACCEPTED` or `REJECTED` decision. An accepted decision is then summarized
  once in append-only `slice-amendments.md`, whose chain determines the exact
  effective commit and packet downstream consumers must accept.

The complete amendment-record schema above is mandatory beginning with A3.
A1 and A2 predate Constitution 2.5.0 and retain their already accepted
historical schemas; they MUST NOT be rewritten to imitate the new procedure.
An A3-or-later record begins with exactly one initialization section containing
`Slice`, `Amendment ID`, `Amended interface`, `Prior interface version`,
`New interface version`, `Prior effective commit`, `Prior effective packet`,
`Starting commit`, `Owner lane`, `Assigned participant / source`,
`Fixed scope paths`, `Amendment task IDs`, `Amendment tasks SHA256`,
`Analysis result`, `Branch`, and `Worktree`. Later phase, candidate, handoff,
and decision facts are appended to that same file. The candidate diff from the
recorded starting commit MUST be contained by `Fixed scope paths`; the starting
commit and candidate MUST both descend from the prior effective commit.

Activation and acceptance records MUST be immutable. Candidate and handoff
files MUST be append-only attempt streams, agree with the bound slice
declarations, and remain absent before their first transition. A later attempt
MUST NOT rewrite or delete an earlier record. Candidate evidence and handoff
packets MUST name existing exact ordinary-path files, and every candidate SHA
MUST identify an existing Git commit descending from the activation starting
commit. The candidate commit MUST contain the bound `tasks.md` whose normalized
manifest is attested and every named candidate evidence file; historical
attempts are checked against their own commit rather than the latest task graph.

Slice `110` program-tail evidence is equally exact. Cutover acceptance MUST
contain program, `CUTOVER_ACCEPTED` status, candidate commit, Zoe as acceptance
owner, ISO date, durable decision reference, and
`Recorded by: v2-program-owner`. Post-merge verification MUST contain program,
`CUTOVER_VERIFIED` status, full accepted-candidate and merged-candidate commits,
`Main ref: refs/heads/main`, the matching full main commit, ISO verification
date, verification commands/results beginning `PASS —`, exact evidence paths,
`Documentation freshness: PASS`, and the full docs/evidence-only
`Documentation commit`. The accepted candidate, merged candidate, verified main
commit, and later documentation commit MUST form one ancestry chain contained
in `refs/heads/main`; the diff from verified main to documentation commit MUST
contain only `README.md`, `CHANGELOG.md`, `docs/`, or `evidence/` changes.

Program progress is derived rather than independently asserted: `PLANNING`
precedes the durable planning-baseline acceptance at
`evidence/governance/slice-lifecycle-amendment-2026-07-11.md`; `READY` means
that record is present and valid and no slice has entered `ACTIVE`; `DELIVERY` begins with the first
`ACTIVE` implementation slice; `INTEGRATION` begins only when slice `110`
enters `ACTIVE`; `CUTOVER_ACCEPTED` requires slice `110` acceptance plus the
explicit Zoe decision record; and `CUTOVER_VERIFIED` additionally requires the
complete post-merge record for the exact main commit and final documentation
validation. A program declaration that does not match those facts is invalid.

Every first delivery or active correction MUST pass this control-plane
sequence:

```text
bind existing slice -> review specification -> clarify -> plan -> review plan ->
checklist -> tasks -> analyze -> review analysis -> implementation
authorization -> slice readiness -> implement -> converge -> documentation
freshness -> slice handoff
```

The planning-only workflow MUST stop after analysis. The delivery workflow MUST
operate on an existing, explicitly bound slice; it MUST NOT create a replacement
feature. It MUST verify implementation authority and then slice-specific
readiness immediately before implementation. It ends when the assigned
participant has established `HANDOFF_READY` and handed the exact packet to the
designated acceptance owner. Acceptance or rejection is a separate act owned by
that recipient; it MUST NOT be fabricated by the delivering participant. The
assigned `v2-integrator` writes acceptance/rejection evidence for `010`–`100`.
For slice `110`, Zoe makes the external decision and the assigned
`v2-integrator` durably copies it into that slice's acceptance or rejection
evidence; Zoe remains `Accepted by`/`Rejected by`. The assigned program owner
copies an accepted Zoe decision only into the program-level cutover record.
Neither recorder becomes the decision owner, and the program owner never writes
another participant's slice evidence.

An accepted amendment uses the same sequence but the readiness, activation,
convergence, documentation, and handoff gates take their amendment branches.
Those branches require a valid current occupant of the stable owner lane, keep
the slice declaration `ACCEPTED`, leave terminal lifecycle evidence unchanged,
write only the fixed amendment record and ordinary amendment scope, and end
before the integrator's separate decision. `speckit-plan`, `speckit-tasks`,
`speckit-implement`, and `speckit-converge` MUST preserve completed history and
operate only on the amendment-scoped plan and task delta.

Before any slice implementation checkbox is completed, the program owner MUST
record Zoe's external grant at
`evidence/governance/v2-implementation-authorization.md`. The single program
record MUST name
program `001-nunchi-v2-program`, status `AUTHORIZED`, every authorized slice
`010` through `110`, Zoe as authorizer, an ISO date, the starting commit, the
commissioned objective, a durable authority reference, and
`Recorded by: v2-program-owner`. It documents
authority granted outside the repository; it MUST NOT grant authority itself or
authorize cutover, release, or promotion. Until it is valid, governance checks
MUST reject every completed slice implementation task. Once valid, it removes
only the program-level lock; a partial record is invalid and leaves every slice
dormant. It does not make a dependency-blocked or unowned
slice `READY`. This is repository governance evidence only and MUST NOT enter
runtime, conversation, classifier, receipt, or social-memory state.

For Nunchi, `spec.md`, `plan.md`, `research.md`, `tasks.md`, and requirement
quality checklists are control-plane artifacts. The standard SpecKit
`data-model.md`, `contracts/`, and `quickstart.md` outputs are prohibited inside
managed paths; interface design, runnable validation guides, machine-readable
contracts, and user documentation MUST instead be created under their ordinary
repository homes during authorized slice implementation. Plans MUST name
those target paths without embedding the product artifacts.

Before implementation, analysis MUST report zero CRITICAL or HIGH findings,
the accountable owner lane MUST have one valid assigned occupant, every
declared dependency MUST be terminally accepted at its exact effective commit
and packet and separately accepted by the consumer, and the slice's acceptance
scenes and evidence locations MUST be concrete. Before integration, the slice owner MUST hand off a commit,
verification commands, evidence references, and known limitations to the final
integrator. That handoff MUST include the reviewed documentation disposition and
validation results.

## Documentation Freshness Gate

Every implementation spec and plan MUST include a documentation-impact review.
The plan MUST name `README.md`, every known affected ordinary-path document, the
accountable documentation task or lane, and validation appropriate to each
claim. The task graph MUST implement that review before handoff; a generic
"update docs" task is not sufficient. A directory wildcard or generic path is
also insufficient when the affected files are already known.

Each reviewed documentation surface MUST receive exactly one disposition:

- **`UPDATE`**: the affected ordinary-path document changes in the candidate,
  and its links, diagrams, examples, commands, and machine-checkable claims are
  validated as applicable.
- **`NO_IMPACT`**: the document remains accurate. The ordinary-path handoff
  evidence MUST list the exact reviewed paths and a concrete rationale. A task
  checkbox or unexplained assertion is not evidence.
- **`HANDOFF`**: a shared or integrator-owned document needs a later edit. The
  slice MUST provide the exact required claim delta and name the accepting
  owner. `HANDOFF` is not `NO_IMPACT`, and it is invalid for documentation the
  slice itself owns.

`README.md` MUST be reviewed for every implementation. Documentation impact
includes changes to behavior, public or inter-component contracts,
configuration/defaults, installation/upgrade, entry points, supported surfaces,
security posture, evidence tier, limitations, version/current/release state,
diagrams, runnable examples, and operator commands. The reviewer MUST reject a
disposition that does not match the exact candidate diff and evidence.

The final integrator owns global current-state wording at an atomic cutover.
When the cutover changes current behavior, `NO_IMPACT` and `HANDOFF` are invalid
for `README.md` and the affected cross-surface documentation: those documents
MUST use `UPDATE` in the accepted candidate. The atomic candidate and merged
main commit MUST say that the cutover is accepted but exact-main verification
and final documentation are pending; they MUST NOT claim that V2 is verified
current behavior. After exact-main verification, the integrator MUST finalize
current-state wording and its validation in the same docs/evidence-only
follow-up that records post-merge verification. `CUTOVER_VERIFIED` is
established only after both the exact-main checks and final documentation pass.
That follow-up MUST contain no product source, schema, runtime, or behavior
change. Actual docs and durable handoff evidence remain in ordinary repository
paths; SpecKit records only the plan, tasks, disposition, ownership, and gate
state.

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
blocks the affected work. Program and slice milestone acceptance requires the
repository governance check and full existing test baseline to pass.

**Version**: 2.5.0 | **Ratified**: 2026-05-22 | **Last Amended**: 2026-07-23
