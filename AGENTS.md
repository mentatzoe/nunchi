# Nunchi Agent Guidelines

Nunchi is a portable pre-attention gate for turn-aware participants in shared
conversation.

## Authority order

Read these before substantive work, in this order:

1. Zoe-selected Aleph Vault Nunchi decisions and technical design, selected in
   PR 67 (`bdd1ebb`) and contract-clarified in PR 68 (`c834e8c`).
2. `.specify/memory/constitution.md`.
3. This file and `CLAUDE.md` for runtime-specific execution guidance.
4. `specs/001-nunchi-v2-program/` and the one owned slice being worked.
5. Ordinary-path source, schemas, tests, evals, evidence, and docs for what is
   currently implemented and proven.

Higher authority wins. SpecKit artifacts organize work; they do not redefine
the selected design or current implementation truth.

## Program and slice lifecycle

The 2026-07-11 governance-reset baseline recorded the V2 program as `READY`,
program implementation authority as `NOT_GRANTED`, and every slice `010`
through `110` as `PLANNED` with its product tasks dormant. That is a dated
snapshot, not a permanently current status table. Before acting, resolve live
program progress from `specs/001-nunchi-v2-program/`, implementation authority
from `evidence/governance/v2-implementation-authorization.md`, and the bound
slice's state and occupant from its declarations plus immutable activation and
acceptance records and append-only candidate/handoff attempt streams. The
planning-baseline amendment distinguishes program `READY` from `PLANNING`.

The repository currently implements V1 (`PASS / ACK / ASK / SPEAK`). The
selected, unimplemented V2 target uses `SUPPRESS / WAKE / DEFER` plus separate
operational `ERROR`, followed by a normal participant act-or-silence turn.
V1 remains current until the atomic V2 merge is verified on `main` and program
state is `CUTOVER_VERIFIED`.
Never describe a planned or partially delivered V2 slice as current behavior.

Program progress and implementation authority are separate facts. Each slice
uses this lifecycle:

```text
PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY -> ACCEPTED
```

- `PLANNED` means its control-plane artifacts agree and implementation is
  dormant.
- `READY` requires the complete program implementation-authority record, one
  assigned participant in the accountable owner lane, accepted upstream
  handoffs recorded as ordered full commits plus matching per-consumer
  acceptance references, zero CRITICAL/HIGH analysis findings, an isolated
  worktree, and ordinary-path activation evidence. Slice `110` requires every
  upstream slice `010`–`100` to be `ACCEPTED`.
- `ACTIVE` is implementation by that owner within the bound slice.
- `CONVERGED` means implementation, tests/evaluations, evidence, task state,
  and limitations agree.
- `HANDOFF_READY` additionally requires documentation freshness for the exact
  candidate and a complete handoff packet.
- `ACCEPTED` means `v2-integrator` accepted the exact commit and packet for
  slices `010`–`100`, or Zoe accepted the exact slice-`110` candidate. Each
  dependent owner separately accepts every required upstream handoff before
  its own slice can become `READY`; dependency acceptance does not replace the
  slice-level acceptance decision. Only slice `110` may integrate and cut over
  the program.

Rejection appends a `REJECTED` handoff decision and returns the same owner to
`ACTIVE`; rework appends a new candidate and handoff without deleting history.
Because the rejected handoff's delivery run already completed, the owner starts
a new bound `run speckit` for that slice and never resumes the completed run.
The same new-run rule applies when convergence appends tasks: retain the
original activation, remain `ACTIVE`, and re-enter through authority and
readiness checks. Fixes requested by a paused post-convergence gate may resume
that run only while its task graph is unchanged.
There is no central mutable slice-state registry. State is derived from the
slice declaration, immutable activation/acceptance records, and append-only
candidate/handoff evidence. These are repository-governance facts only:
they MUST NOT become a runtime registry, conversation state, classifier input,
receipt field, participant roster, social ledger, or memory service.

## SpecKit execution spine

- Required CLI version: exactly `0.12.11`.
- Installed integrations: Codex and Claude; Codex is the default.
- Both workflows operate on one existing slice. Invoke them only through
  `scripts/run_slice_workflow.py`; it runs the canonical preflight, sets the
  slice environment in the workflow process, pins the slice input, integration
  manifest and installed skill bytes, workflow digest, and initial task graph,
  and leaves `.specify/feature.json`
  unchanged.
- Planning-only existing-slice workflow: `nunchi-plan`. It never creates or
  replaces a feature.
- Existing-slice delivery workflow: `speckit`. Its implementation-authority
  and slice-readiness gates are mandatory before `implement`; it ends at
  `HANDOFF_READY`, before the recipient's separate acceptance or rejection.
- Each slice has one accountable owner lane. Reviewers do not silently co-own.
- The assigned slice participant writes only that slice's declarations and
  lifecycle evidence; `v2-program-owner` writes program facts and never another
  participant's slice evidence. `v2-integrator` records every slice acceptance
  or rejection; for slice `110`, it copies Zoe's decision without owning it.
- Use isolated worktrees for non-trivial slice implementation.

Invoke the selected workflow with the exact bound slice:

```sh
python3 scripts/run_slice_workflow.py run nunchi-plan specs/<exact-slice>
python3 scripts/run_slice_workflow.py run speckit specs/<exact-slice>
python3 scripts/run_slice_workflow.py resume <run-id>
```

An initial `run` may append `--integration claude` or `--integration codex`;
the runner pins that choice, its manifest, and the exact installed skill bytes;
resume cannot change them.
The runner verifies exact SpecKit `0.12.11` and its pinned PEP-610 source commit
before both run and resume, then resolves and pins the concrete integration.

The implementation-authority record is
`evidence/governance/v2-implementation-authorization.md`. It documents Zoe's
external grant for the complete program and MUST enumerate exactly all eleven
slices (`010` through `110`). A partial or extra-scope record is invalid and
keeps every slice dormant. The record does not grant authority itself, make any
slice `READY`, or authorize cutover, release, or promotion. The assigned
`v2-program-owner` copies the external decision and includes `Recorded by:
v2-program-owner`. Slice readiness is checked separately against its
dependencies, owner, analysis, worktree, and activation evidence.

Zoe, or an assigner named in a durable delegation from Zoe, may assign the
`v2-program-owner` lane and a participant to each slice owner lane. Record a
slice occupant as `<participant identity>` —
`evidence/governance/assignments/<record>.md`. That non-symlink record MUST have
exactly one `Assignee`, `Lane`, `Assigned by`, ISO `Assigned on`, and durable
`Authority reference`. When `Assigned by` is not Zoe, it also MUST have
`Delegated by: Zoe` and a durable `Delegation reference`. Transient chat or
session memory is not a durable assignment. Assignment may precede
implementation
authority so planning can proceed, but it does not authorize implementation or
make a slice `READY`. Keep assignment in the program or bound-slice declaration
and copy it into activation evidence; never create a central assignment
registry.

Slice `110` has a separate program tail after its delivery workflow reaches
`HANDOFF_READY`. Zoe's durable exact-candidate decision is recorded in
`evidence/v2/parity/slice-acceptance.md` by the assigned `v2-integrator`; on
acceptance, the assigned `v2-program-owner` records only the program-level copy
in `evidence/v2/parity/cutover-acceptance.md`. This establishes slice
`ACCEPTED` and program `CUTOVER_ACCEPTED`. The integrator may then perform one
atomic merge. That merge remains verification-pending and MUST NOT present V2
as verified current behavior. Only exact-main verification plus final
current-state documentation validation, recorded together in a docs/evidence-
only follow-up at `evidence/v2/parity/post-merge-verification.md`, establishes
`CUTOVER_VERIFIED`; release and promotion remain separate decisions.

SpecKit-managed paths are control plane only:

- `.specify/`
- `specs/`
- `.agents/skills/speckit-*`
- `.claude/skills/speckit-*`

They may contain tool configuration, constitution, specs, plans, planning
research, requirement-quality checklists, tasks, owners, dependencies, and
workflow state. They may never contain product source, machine-readable
contracts/schemas, executable tests, fixtures, eval runners/corpora, evidence,
runtime assets, or product documentation.

Product artifacts belong under `src/`, `schemas/`, `tests/`, `evals/`,
`evidence/`, `integrations/`, `scripts/`, and `docs/`. Build, test, eval, docs,
packaging, release, and runtime commands must not depend on managed paths.

The standard SpecKit plan command normally proposes `data-model.md`,
`contracts/`, and `quickstart.md` inside a feature directory. Nunchi's
constitution forbids those outputs. Record interface and validation planning in
`plan.md`; create actual schemas/contracts under `schemas/` and runnable guides
under `docs/` only during authorized slice implementation.

## Documentation freshness

Documentation is a blocking part of every implementation slice. Each spec,
plan, and task graph must explicitly review `README.md` and every ordinary-path
document affected by behavior, interfaces, configuration/defaults,
installation, entry points, supported surfaces, security posture, evidence
grade, limitations, version/current state, diagrams, examples, or commands.

Use exactly one disposition per reviewed surface:

- `UPDATE`: land and validate the affected docs with the candidate.
- `NO_IMPACT`: list exact reviewed paths and concrete rationale in ordinary
  handoff evidence.
- `HANDOFF`: for shared/integrator-owned docs only, provide the exact required
  claim delta and accepting owner. It is not a no-impact finding.

Name exact affected files; a generic directory or wildcard is not a review when
the paths are already known. Slice task checkboxes remain dormant until the
external grant is documented at
`evidence/governance/v2-implementation-authorization.md`, enumerates exactly
all slices `010` through `110`, and the separate slice-readiness gate passes.

Intermediate V2 slices update their owned component docs and hand global
current-state wording to `v2-integrator`; they must not claim partial V2 as
current. Slice `110` must update `README.md` and affected cross-surface docs as
part of the atomic cutover, while truthfully marking the merged candidate
`CUTOVER_ACCEPTED` with exact-main verification and final documentation
pending. After exact-main verification, a docs/evidence-only follow-up finalizes
and validates current-state wording; only then may the program become
`CUTOVER_VERIFIED`. No implementation may converge or hand off until the
documentation-freshness gate passes for the exact candidate.

## Product invariants

- Only a participant-shaped model may make a social suppression judgment.
- Deterministic code handles transport-proven non-events, never conversational
  meaning.
- Uncertainty wakes or defers.
- Trusted preattention bypass wakes directly with no fabricated model result.
- Exact self binding is separate from loose names and aliases.
- Context is bounded, structured, coverage-honest, and optionally expandable.
- Continuation authority is host-only; the classifier sees no opaque handle,
  binding, cursor, expiry, or fetch secret.
- Observation, attention, participant-host, and transport receipts are
  immutable, request-correlated, and singly attested by their owner.
- There is no social handled/open ledger, obligation queue, or inferred roster.
- Preattention is judged once; no send-time social reclassification.
- A woken participant contributes directly or sends nothing; no meta-answer.
- V2 must cut over atomically across all in-tree consumers and prove parity.

## Commands

```sh
python3 scripts/check_governance.py --check-cli
python3 -m unittest
python3 -m evals.verdict_suite.runner --list
```

The test suite is stdlib `unittest`, offline, and deterministic unless a command
explicitly performs a live provider evaluation. Current package/runtime details
remain in `CLAUDE.md`, `README.md`, and `docs/`.

## Definition of done

A slice is ready only when its spec, plan, tasks, owner, dependencies,
interfaces, integration strategy, acceptance scenes, and evidence requirements
agree; analysis has no CRITICAL/HIGH findings; and the governance boundary
passes. Product completion additionally requires ordinary-path implementation,
tests, evidence, installed-runtime provenance, accepted README/docs
dispositions and validation, and integrator handoff.
