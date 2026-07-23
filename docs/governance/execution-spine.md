# Nunchi V2 execution spine

This document explains how Nunchi uses SpecKit after the V2 governance reset.
It is ordinary repository documentation; the executable planning state itself
lives in the disposable SpecKit control plane.

## Authority

The source-of-truth order is:

1. Repository-owned `docs/architecture/v2-selected-design.md` and
   `docs/contracts/nunchi-v2.md`, preserving the Zoe-selected Aleph Vault
   decisions from PR 67 (`bdd1ebb`) and PR 68 (`c834e8c`).
2. `.specify/memory/constitution.md`.
3. `AGENTS.md` and `CLAUDE.md`.
4. `specs/001-nunchi-v2-program/` and its independently owned slices.
5. Ordinary-path implementation, tests, evaluations, evidence, and product
   documentation for what is currently built and proven.

The repository-owned design owns the selected target; the historical Vault
commits establish provenance only. The repository's ordinary artifacts own
current implementation truth. SpecKit owns execution planning only.

## Program authority and slice lifecycle

At the 2026-07-11 governance-reset baseline, the program was `READY`, program
implementation authority was `NOT_GRANTED`, and every slice `010` through
`110` was `PLANNED` with every implementation task dormant. That is an
immutable dated snapshot, not a permanent status table. A human, Claude,
Codex, or other participant resolves live program progress from the umbrella
declaration in `specs/001-nunchi-v2-program/`, implementation authority from
the exact record at
`evidence/governance/v2-implementation-authorization.md`, and slice state and
occupant from the bound slice declarations, immutable activation/acceptance
records, and append-only candidate/handoff attempt streams. No participant-
local execution state or centrally maintained documentation table establishes
live state.

The current audited baseline is
`evidence/v2/completion-baseline-2026-07-23.md`: slice `010` is terminally
accepted through amendments A1/A2, its effective dependency commit is
`26a6b531fa146ba1f1f5fcd1c4d191041b141301`, and the selected completion target
still lacks accepted `I-010F`. Slices `020`–`110` are `PLANNED`; the runnable
product remains V1. No historical downstream branch or packet changes those
facts.

Program progress is:

```text
PLANNING -> READY -> DELIVERY -> INTEGRATION -> CUTOVER_ACCEPTED ->
CUTOVER_VERIFIED
```

The dated amendment at
`evidence/governance/slice-lifecycle-amendment-2026-07-11.md` is the durable
planning-baseline acceptance that distinguishes `READY` from `PLANNING`.

Implementation authority is a separate `NOT_GRANTED | GRANTED` fact. Each
slice progresses independently:

```text
PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY -> ACCEPTED
```

`READY` means the complete program authorization record is valid, the slice's
named participant occupies the owner lane from a durable assignment source,
all declared upstream slices are terminally `ACCEPTED` at exact current
effective commits and their terminal or amendment packets have matching
per-consumer acceptance references, analysis is clean, its isolated worktree is
fixed, and its `slice-activation.md` records those exact facts.
There is no central status registry: state is derived from the slice declaration
and its activation, candidate, handoff, and acceptance evidence. None of this
state enters conversation, classifier, runtime permission, receipt, or social
memory.

At slice level, `v2-integrator` accepts the exact commit and handoff packet for
slices `010`–`100`; Zoe accepts the exact slice-`110` candidate. Separately,
each dependent owner must accept each required upstream packet before its own
slice may become `READY`. Both facts are required: terminal upstream acceptance
does not fabricate consumer acceptance, and consumer acceptance cannot make a
nonterminal upstream candidate ready for dependency use.

Create the following record only after Zoe externally grants implementation
authority for the complete V2 program:

```markdown
# Nunchi V2 Implementation Authorization

**Program**: `001-nunchi-v2-program`

**Status**: AUTHORIZED

**Authorized slices**: 010, 020, 030, 040, 050, 060, 070, 080, 090, 100, 110

**Authorized by**: Zoe

**Authorized on**: YYYY-MM-DD

**Starting commit**: `<full-40-character-sha>`

**Commissioned objective**: <the authorized V2 implementation scope>

**Authority reference**: <durable external decision reference>

**Recorded by**: v2-program-owner

This record documents externally granted implementation authority; it does not
grant it and does not authorize cutover, release, or promotion.
```

The record lives at
`evidence/governance/v2-implementation-authorization.md`. Its absence or an
incomplete, duplicate, or extra-scope slice list makes the record invalid and
keeps every implementation checkbox locked. It must enumerate exactly `010`,
`020`, `030`, `040`, `050`, `060`, `070`, `080`, `090`, `100`, and `110`; there
is no partial slice authorization. A valid record removes only the program-level
lock; it does not make an unassigned or dependency-blocked slice `READY`.

### Assignment contract

Zoe may assign the `v2-program-owner` and each slice owner-lane occupant. An
assigner may act for Zoe only when a durable Zoe decision explicitly delegates
that assignment authority. Record an occupant in the program or bound slice as:

```text
<participant identity> — evidence/governance/assignments/<record>.md
```

The referenced non-symlink record must contain exactly one `Assignee`, `Lane`,
`Assigned by`, ISO `Assigned on`, and durable `Authority reference`. When
`Assigned by` is not Zoe, it must also contain `Delegated by: Zoe` and a durable
`Delegation reference`. A transient chat message, participant session, or
private memory is not sufficient.

Copy one record per assignment:

```markdown
# Nunchi V2 Assignment

**Assignee**: <participant identity>
**Lane**: <exact program role or slice owner lane>
**Assigned by**: Zoe
**Assigned on**: YYYY-MM-DD
**Authority reference**: <durable URL, commit, or repository decision>

<!-- Include both lines only when Assigned by is not Zoe. -->
**Delegated by**: Zoe
**Delegation reference**: <durable Zoe delegation>
```

Assignment may happen before implementation authority so that planning can
proceed, but it neither grants implementation authority nor makes a slice
`READY`. The activation record copies the same assignment fact when the slice
becomes ready. Do not build a central assignment registry; program and slice
declarations plus immutable activation evidence are sufficient.

### Slice activation matrix

| Slice | Owner lane | May become `READY` after | Activation evidence | Slice-level acceptance |
|---|---|---|---|---|
| `010` | `v2-contract-owner` | Program authority is granted | `evidence/v2/contract/slice-activation.md` | `v2-integrator` |
| `020` | `v2-observation-owner` | Its `010` handoff is accepted | `evidence/v2/observation/slice-activation.md` | `v2-integrator` |
| `030` | `v2-core-owner` | Its `010` handoff is accepted | `evidence/v2/attention/slice-activation.md` | `v2-integrator` |
| `040` | `v2-wake-owner` | Its `010`, `020`, `030` handoffs are accepted | `evidence/v2/participant/slice-activation.md` | `v2-integrator` |
| `050` | `v2-transport-owner` | Its `010`, `020` handoffs are accepted | `evidence/v2/discord-transport/slice-activation.md` | `v2-integrator` |
| `060` | `v2-hermes-owner` | Its declared `010`–`040` handoffs are accepted | `evidence/v2/hermes/slice-activation.md` | `v2-integrator` |
| `070` | `v2-claude-owner` | Its declared `010`–`050` handoffs are accepted | `evidence/v2/claude-code/slice-activation.md` | `v2-integrator` |
| `080` | `v2-codex-owner` | Its declared `010`–`050` handoffs are accepted | `evidence/v2/codex/slice-activation.md` | `v2-integrator` |
| `090` | `v2-adapters-owner` | Its declared `010`–`040` handoffs are accepted | `evidence/v2/adapters/slice-activation.md` | `v2-integrator` |
| `100` | `v2-security-owner` | Its declared `010`–`090` handoffs are accepted | `evidence/v2/security/slice-activation.md` | `v2-integrator` |
| `110` | `v2-integrator` | Every slice `010`–`100` is `ACCEPTED` | `evidence/v2/parity/slice-activation.md` | Zoe |

### Transition evidence schema

Each slice keeps four lifecycle files. Activation and acceptance are immutable;
candidate and handoff are append-only attempt streams. They are independent
attestations, not rows in an aggregate registry.

| File | Establishes | Required metadata |
|---|---|---|
| `slice-activation.md` | `READY` | `Slice`, `Status: READY`, `Assigned participant / source`, exact `Authority record`, canonical `Accepted dependencies`, ordered `Dependency commits` as `slice=full-sha`, ordered `Dependency acceptance references` as `slice=consumer-owned-evidence-file`, `Analysis result: PASS — zero CRITICAL/HIGH findings`, `Branch`, `Worktree`, full `Starting commit`, exact plan-enumerated `Interfaces` and `Acceptance scenes`, exact planned `Evidence targets`, the complete planned `Documentation scope`, exact `Initial task IDs`, and normalized `Initial tasks SHA256`; the three dependency fields are `none` for `010` |
| `slice-candidate.md` | `CONVERGED` | Append one attempt with `Slice`, `Status: CONVERGED`, a full `Candidate commit` descending from the activation commit and containing the bound tasks/evidence, exact commit-local `Completed task IDs`, matching normalized `Tasks SHA256`, `Tasks complete: YES`, `Verification commands / results` beginning `PASS —`, `Interface versions`, exact existing commit-local `Evidence paths`, and `Known limitations` |
| `slice-handoff.md` | `HANDOFF_READY` or retry | Append a handoff attempt with `Slice`, `Status: HANDOFF_READY`, matching `Candidate commit`, `Acceptance owner`, `Documentation freshness: PASS`, and exact existing `Packet paths`; rejection appends `Slice`, `Status: REJECTED`, rejected `Candidate commit`, `Rejected by`, ISO `Rejected on`, durable `Decision reference`, and `Recorded by: v2-integrator` |
| `slice-acceptance.md` | `ACCEPTED` | `Slice`, `Status: ACCEPTED`, matching `Candidate commit`, `Accepted by`, ISO `Accepted on`, durable `Decision reference`, and `Recorded by: v2-integrator` |
| `amendment-<id>-<scope>.md` | bounded successor attempt while the slice stays `ACCEPTED` | One append-only record fixing stable owner lane, current participant/assignment, amendment ID, interface and versions, current effective predecessor commit and packet, ordinary-path scope, task manifest, evidence and docs obligations; later sections add exact candidate, verification, limitations, `HANDOFF_READY` packet, and integrator `ACCEPTED` or `REJECTED` decision |
| `slice-amendments.md` | accepted effective dependency chain | Append exactly one summary per accepted amendment, chaining prior effective commit to accepted successor commit and naming the accepted amendment packet; rejection never changes this ledger |
| `parity/cutover-acceptance.md` | `CUTOVER_ACCEPTED` | `Program: 001-nunchi-v2-program`, `Status: CUTOVER_ACCEPTED`, `Accepted by: Zoe`, `Recorded by: v2-program-owner`, matching `Candidate commit`, ISO `Accepted on`, and durable `Decision reference` |
| `parity/post-merge-verification.md` | `CUTOVER_VERIFIED` | `Program: 001-nunchi-v2-program`, `Status: CUTOVER_VERIFIED`, full `Accepted candidate commit`, full `Merged candidate commit`, `Main ref: refs/heads/main`, full verified `Main commit`, ISO `Verified on`, `Verification commands / results` beginning `PASS —`, exact `Evidence paths`, `Documentation freshness: PASS`, and a later full `Documentation commit`; accepted → merged → verified-main → docs/evidence-only follow-up must be one ancestry chain contained in `main` |

Generate the exact task fields for activation or a candidate attempt instead of
reverse-engineering normalization:

```sh
python3 scripts/check_governance.py --task-manifest specs/<exact-slice>
```

The participant writes `slice-activation.md` only after every readiness fact is
accepted; that record and matching declarations establish `READY` before the
declarations move to `ACTIVE`. Candidate and handoff files are append-only
attempt streams; activation and acceptance records are immutable. On rejection,
the designated recorder appends the rejection decision and the slice returns
to `ACTIVE`. For slice `110`, the assigned integrator records Zoe's decision;
Zoe remains `Rejected by`. Because that delivery run already completed, the
assigned participant starts a new bound `run speckit` for the same slice and
never resumes it. If convergence adds tasks, the slice stays `ACTIVE`, retains
the original activation, and likewise starts a new bound run. Fixes requested
by a paused post-convergence gate may resume the same run only when the task
graph is unchanged. Every later candidate and handoff attempt appends while
preserving prior history.
Candidate commits must exist in Git, and candidate evidence and handoff packet
paths must name existing ordinary-path files. For slices `010`–`100`, `Accepted by` is
`v2-integrator`; for `110`, it is Zoe. Each dependent's upstream acceptance is
also named in that dependent's activation evidence and remains separate from
slice-level acceptance.

Each referenced dependency-acceptance file lives under the consumer's evidence
directory, includes the upstream ID in its filename, and records `Consumer
slice`, `Upstream slice`, matching `Candidate commit`, `Accepted by`, ISO
`Accepted on`, exact upstream `Packet reference`, and a durable `Decision
reference`. This proves the consumer's decision without inventing a shared
acceptance registry.

If an accepted upstream amendment changes that effective binding after a
dependent activated, the dependent's activation and earlier decisions remain
immutable historical facts. The dependent candidate is nevertheless blocked
from further use until its owner appends a compatibility re-attestation naming
the exact new effective commit and packet, affected candidate, verification
commands/results, and `PASS` or `INCOMPATIBLE`. `PASS` establishes only the new
consumer binding; it does not rewrite activation or upstream acceptance.
`INCOMPATIBLE` requires a replacement dependent candidate.

### Bounded post-acceptance amendment

An accepted slice does not move backward to `READY` or `ACTIVE` to publish a
versioned successor. The current occupant of its stable owner lane starts a new
bound `speckit` run in accepted-amendment mode. The slice declaration remains
`ACCEPTED`, and its `slice-activation.md`, terminal `slice-candidate.md`,
terminal `slice-handoff.md`, `slice-acceptance.md`, and earlier amendments stay
byte-for-byte unchanged.

Before implementation, the amendment record fixes its complete scope. From A3
onward it must contain the full schema shown above; A1/A2 retain the schema
under which they were accepted and are not rewritten retroactively. The
candidate must descend from the exact current effective predecessor. Workflow
convergence and documentation gates write candidate and packet sections only
to that amendment record. After the workflow ends at amendment
`HANDOFF_READY`, `v2-integrator` separately appends `ACCEPTED` or `REJECTED`.
Rejection preserves the prior effective commit and packet and requires a fresh
bound amendment run. Acceptance alone permits one append to
`slice-amendments.md`; future consumers must accept that exact successor and
amendment packet.

The next required use is
`evidence/v2/contract/amendment-A3-privileged-action-authorization.md` for
`I-010F PrivilegedActionAuthorizationV2@1`, based on effective predecessor
`26a6b531fa146ba1f1f5fcd1c4d191041b141301` and its A2 packet. Until A3 is
accepted and recorded in the ledger, no slice `020` or later may begin V2
implementation.

Slice `110` additionally has a program tail after its bound-slice delivery
workflow reaches `HANDOFF_READY`. Zoe evaluates the exact candidate. Her durable
decision is copied into `evidence/v2/parity/slice-acceptance.md` by the assigned
`v2-integrator`; on acceptance, the assigned `v2-program-owner` copies it only
into `evidence/v2/parity/cutover-acceptance.md`. This establishes slice
`ACCEPTED` and program `CUTOVER_ACCEPTED`. The integrator may then perform one
atomic merge. The merged candidate remains verification-pending and may say
`CUTOVER_ACCEPTED`, but it must not describe V2 as verified current behavior.
Exact-main verification is recorded against the merge-line commit. Final
current-state documentation then lands in a later docs/evidence-only commit on
the same `main` ancestry; the durable record may land after that referenced
commit without trying to name its own Git SHA. The complete record lives at
`evidence/v2/parity/post-merge-verification.md`; only that complete record
establishes `CUTOVER_VERIFIED`. The program tail does not authorize release or
promotion.

### Participant action contract

| Action | Required facts |
|---|---|
| Plan | Existing bound slice; a durable participant assignment may be recorded before implementation authority, which is not required for planning through analysis. |
| Implement | The complete program authority record is valid; participant assignment, clean analysis, ordered upstream commit/acceptance-reference mappings, branch/worktree, and activation evidence make the bound slice `READY`. Slice `110` additionally requires every upstream slice to be `ACCEPTED`. |
| Amend accepted slice | Stable owner lane with one valid current occupant; complete fixed amendment record; exact effective predecessor commit and packet; clean analysis; terminal history unchanged. The slice remains `ACCEPTED`. |
| Hand off | Slice is converged; planned tests/evaluations/evidence pass; documentation freshness passes; exact commit/interface/provenance/limitations packet exists. |
| Accept dependency | Each dependent owner accepts its own required effective upstream commit and terminal or amendment packet before the dependent slice becomes `READY`; this is distinct from terminal slice acceptance. A later successor requires append-only compatibility re-attestation before an affected candidate is used again. |
| Accept or reject slice | After the delivery workflow ends at `HANDOFF_READY`, `v2-integrator` accepts or rejects slices `010`–`100`; Zoe accepts or rejects the exact slice-`110` candidate. Rejection appends evidence, returns the same owner to `ACTIVE`, and requires a new bound delivery run. |
| Integrate | Only `v2-integrator` in slice `110` assembles the cross-surface candidate from its accepted upstream handoffs. |
| Complete program tail | After slice `110` is `HANDOFF_READY`, the integrator records Zoe's exact-candidate decision for the slice and, on acceptance, the program owner records only the program cutover copy. One atomic merge remains verification-pending; exact-main verification plus final docs validation in a docs/evidence-only follow-up establish `CUTOVER_VERIFIED`. Release remains separate. |

### Who writes what

| Fact or record | Accountable writer | Boundary |
|---|---|---|
| Program or slice assignment decision | Zoe, or the assigner named by Zoe's durable delegation | May be recorded during planning; grants no implementation authority and creates no assignment registry. |
| Complete program implementation-authority record | Assigned `v2-program-owner`, copying Zoe's external all-eleven-slice decision | Synchronizes only the global authority fact; does not assign, activate, or implement a slice. |
| Umbrella program-state declaration | Assigned `v2-program-owner` | Derived from accepted planning baseline, slice transitions, and cutover evidence; the program owner never writes another participant's slice evidence. |
| Slice declarations, activation, candidate attempts, and handoff attempts | Participant assigned to that exact slice's owner lane | Writes only the bound slice; candidate and handoff streams are append-only. |
| Per-consumer dependency acceptance | Participant assigned to the dependent slice | Records the exact effective upstream commit and terminal or amendment packet it accepted under the consumer's evidence directory. |
| Accepted-slice amendment attempt | Current participant assigned to the accepted slice's stable owner lane | Appends only the fixed amendment record and changes only its bounded ordinary-path scope; terminal lifecycle evidence stays immutable. |
| Amendment decision and effective ledger append | `v2-integrator` | Appends `ACCEPTED` or `REJECTED` to the amendment record; only acceptance appends one chained entry to `slice-amendments.md`. |
| Post-activation compatibility re-attestation | Participant assigned to the dependent slice | Appends exact successor commit/packet, affected candidate, verification, and pass/incompatible result; never rewrites activation. |
| Slice acceptance or rejection for `010`–`100` | `v2-integrator` | Acceptance writes `slice-acceptance.md`; rejection appends to that slice's handoff stream and returns the same owner to `ACTIVE`. |
| Slice-`110` decision | Zoe, durably copied into slice acceptance/rejection evidence by the assigned `v2-integrator` | Establishes slice `ACCEPTED` or returns it to `ACTIVE`; the recorder does not own Zoe's decision. |
| Program cutover decision | Assigned `v2-program-owner`, copying the accepted Zoe decision into `cutover-acceptance.md` | Establishes program `CUTOVER_ACCEPTED`; the program owner writes no slice evidence and this does not establish verification or release. |
| Atomic merge and exact-main verification | `v2-integrator`, with program state updated by `v2-program-owner` from the complete post-merge record | The merge remains `CUTOVER_ACCEPTED`; exact-main verification and final documentation validation in one docs/evidence-only follow-up establish `CUTOVER_VERIFIED`. Only then may docs describe V2 as current. |

Reviewers verify these records but do not acquire their writers' ownership.
The table is an authority map, not a mutable assignment or status registry.

## Pinned installation

The generated version pin is `.specify/init-options.json`:

```json
"speckit_version": "0.12.11"
```

`.specify/speckit-lock.json` additionally records that upstream tag
`v0.12.11` resolved to commit
`e802a7dd52a6eceba9403cbbf40e60dced043238`. Install the immutable commit:

```sh
uv tool install specify-cli --force \
  --from 'git+https://github.com/github/spec-kit.git@e802a7dd52a6eceba9403cbbf40e60dced043238'
specify --version
```

Initialize from a truly clean control plane:

```sh
specify init --here --force --integration codex --script sh
specify integration install claude --script sh
specify integration use codex
```

Codex and Claude are both installed; Codex is the default. The optional git and
agent-context extensions are intentionally absent so generated tooling does not
own commits, branches, `AGENTS.md`, or `CLAUDE.md`.

After an upstream refresh, restore or reapply Nunchi's constitution, customized
templates, workflows, and program artifacts from reviewable VCS changes before
planning. Do not preserve an old `.specify/` tree across a major reset.

## Control-plane boundary

Managed paths:

- `.specify/`
- `specs/`
- `.agents/skills/speckit-*`
- `.claude/skills/speckit-*`

Allowed content is limited to tool state, constitution, planning specs and
plans, planning research, requirement-quality checklists, task lists, ownership,
dependencies, and workflows. Product code, schemas/contracts, tests, fixtures,
evaluation runners/corpora, evidence, runtime assets, and product docs belong in
normal repository directories.

The standard SpecKit plan skill normally creates `data-model.md`, `contracts/`,
and `quickstart.md` under a feature. Nunchi forbids those outputs. Plans record
interface summaries and ordinary target paths; authorized slices write contracts to
`schemas/`, tests to `tests/`, evals to `evals/`, evidence to `evidence/`, and
documentation to `docs/`.

Run the mechanical boundary and version check with:

```sh
python3 scripts/check_governance.py --check-cli
```

With `--check-cli`, validation checks both `specify --version` and uv's PEP 610
installation metadata, including the exact resolved Git commit. A same-version
tool installed from another source or commit therefore fails the gate.

CI runs the same repository-boundary checks without requiring a globally
installed SpecKit CLI.

## Workflows

Inspect the workflow definitions without running them:

```sh
specify workflow info nunchi-plan
specify workflow info speckit
```

`Nunchi Existing-Slice Planning Cycle` version `1.4.0` starts by binding that
existing slice, then runs review, clarification, planning, plan review,
requirements checklist, task generation, analysis, and a planning-exit gate.
It does not run `speckit.specify`, create or replace a feature, or implement.
`Nunchi Existing-Slice Delivery Cycle` version `2.6.0` supports first
delivery, active correction/rework, and the bounded accepted-amendment branch
described above. Every mode stays within one bound slice and owner lane.

Both workflows operate on an existing slice. Never rely on the tracked
`.specify/feature.json`, which points to the umbrella planning program. Use the
bound runner so preflight, environment binding, run input, and workflow digest
are one operation. Run the planning-only workflow for one slice with:

```sh
python3 scripts/run_slice_workflow.py run nunchi-plan \
  specs/030-v2-core-attention
```

Run the delivery workflow for that same slice only after program
authorization and slice readiness can pass:

```sh
python3 scripts/run_slice_workflow.py run speckit \
  specs/030-v2-core-attention
```

The default integration, its manifest, and its exact installed skill bytes are
pinned by the runner. To select a supported runtime
explicitly, append `--integration claude` or `--integration codex` to the
initial `run` command. Resume keeps that integration immutable.

Replace `030-v2-core-attention` with the assigned existing slice. The runner's
preflight allowlists only the existing `010`–`110` directories, verifies exact
SpecKit `0.12.11` plus its pinned PEP-610 source commit, verifies required
planning artifacts, confirms the underlying SpecKit resolver returns that exact
directory, resolves the concrete integration, and sets the binding in the
workflow process without modifying `.specify/feature.json`. It verifies CLI
provenance and records a run ID, slice, integration-manifest digest, canonical
and persisted workflow digests, and initial task-graph digest. Resume a paused
bound run only with:

```sh
python3 scripts/run_slice_workflow.py resume <run-id>
```

Resume rejects a changed slice input, integration, CLI provenance, canonical
workflow, persisted workflow copy, integration manifest or installed skill,
or SpecKit run state. The wrapper permits exactly one task-graph transition
only when a resume crosses the workflow's unique successful `speckit.tasks`
step. It records the initial and current task digests, transition timestamp,
step, and before/after state digests; mutation before that boundary, after it,
during repair, or on a later resume fails closed. Convergence-added tasks or a
rejected completed handoff require a new bound delivery run for the same
`ACTIVE` slice; the original activation remains valid and authority/readiness
are rechecked. An accepted-amendment run likewise restarts after rejection or
new convergence tasks while preserving terminal history and the prior
effective binding. The workflow does not run `speckit.specify` or create a
replacement feature; it verifies implementation authority, then slice-specific
readiness, before implementation. It ends in a slice handoff. Only slice `110`
may integrate accepted slice commits, and its program tail is outside every
other slice's delivery cycle.

The delivery workflow makes every owner-controlled declaration transition explicit:

```text
bind existing slice -> review/plan/analyze -> implementation authorization ->
slice readiness or accepted-amendment readiness -> activate or retain ACCEPTED
-> implement -> converge -> record
CONVERGED -> documentation freshness -> prepare HANDOFF_READY -> hand off slice
```

`record-convergence`, documentation freshness, handoff preparation, and slice
handoff pause on retry. A corrective edit with an unchanged task graph resumes
that paused run. When convergence adds tasks, the changed graph invalidates
resume and the owner starts a new bound run from the still-`ACTIVE` slice.
Recipient rejection occurs after the run completed and therefore also starts a
new run; it never jumps directly back into implementation.

The activation record establishes `READY`; the assigned participant then moves
the bound declarations to `ACTIVE` before checking an implementation task.
Candidate and handoff evidence respectively establish `CONVERGED` and
`HANDOFF_READY` and must agree with those declarations. For slices `010`–`100`,
the integrator's exact-candidate acceptance then establishes `ACCEPTED`. For
slice `110`, Zoe's acceptance and the remaining program-tail evidence follow
the separate sequence described above.
In accepted-amendment mode those same gates record amendment convergence and
handoff without changing slice lifecycle declarations. The integrator's
separate decision changes only the effective amendment ledger on acceptance.

## Documentation freshness

Every implementation plan contains an exact documentation-impact matrix. It
must review `README.md` and each relevant ordinary-path document, then assign:

- `UPDATE` when the candidate must change and validate the document;
- `NO_IMPACT` only with exact reviewed paths and concrete rationale in ordinary
  handoff evidence; or
- `HANDOFF` only for shared or integrator-owned wording, with the exact claim
  delta and accepting owner.

Name each known affected file. Generic directory rows and wildcards are invalid
when the plan can identify the actual documents.

The workflow's `documentation-freshness` gate runs after convergence and before
slice handoff. It reviews the exact candidate rather than trusting a task
checkbox. Links, Mermaid, examples, commands, install/version claims, and
machine-checkable truthfulness tests are validated when relevant. Intermediate
V2 slices update their component docs and hand global current-state deltas to
`v2-integrator`; slice `110` updates `README.md` and affected cross-surface docs
as part of the atomic cutover without claiming verified-current behavior. The
merged candidate may truthfully say `CUTOVER_ACCEPTED` with exact-main
verification and final current-state documentation pending. After exact-main
verification, the integrator finalizes current-state wording and validates it
in the same docs/evidence-only follow-up; only then may the program become
`CUTOVER_VERIFIED`. That follow-up changes no product source, schema, runtime,
or behavior.

`scripts/check_governance.py` mechanically enforces the required sections,
README disposition, owned-doc update, tasks, checklist coverage, and workflow
order. It cannot infer whether prose is socially or technically truthful; that
remains the exact-candidate review gate, strengthened by focused truthfulness
tests for claims that can be compared to code.

## Ownership model

The umbrella program defines stable owner lanes. A participant occupies a lane
only through the assignment contract above, recorded in the program or bound
slice declaration and copied into that slice's activation evidence. Two lanes
never co-own a slice, and reviewers never acquire ownership by editing it. A
lane handoff requires a new durable Zoe or delegated-assigner decision that
records the outgoing and incoming owner; it is not a mutable registry entry.

Each slice plan names:

- one accountable owner lane;
- the assigned participant/source and slice activation evidence path;
- upstream and downstream slice IDs;
- consumed and produced interfaces;
- isolated worktree/branch and integration order;
- acceptance scenes;
- deterministic and live evidence targets;
- the exact handoff packet required by the final integrator.

The program structure and selected product lifecycle are also available as
renderable Mermaid component, class, sequence, state, and execution-wave views
in [`../architecture/v2-selected-design.md`](../architecture/v2-selected-design.md).

## Reinitialization safety

The control plane is safe to delete when:

1. `python3 scripts/check_governance.py` passes;
2. no build, test, eval, docs, package, release, or runtime command references a
   managed path;
3. `python3 -m unittest` and ordinary eval smoke commands still run with the
   managed paths absent.

In a disposable copy where the control plane has deliberately been removed,
run the product baseline as:

```sh
NUNCHI_SKIP_GOVERNANCE_TESTS=1 python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

Only `tests/test_governance.py` is skipped by that explicit environment flag;
the pre-reset 968 product tests still execute. Never set the flag in CI or in a
normal checkout: CI first runs `scripts/check_governance.py`, and the complete
suite exercises the governance tests when `.specify/` is present.

Deletion loses planning state, not product truth. VCS preserves reviewed
planning history, and a fresh pinned init recreates the tooling surface.
