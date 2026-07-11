# Slice-centric execution-spine amendment — 2026-07-11

## Claim boundary

This record proves the governance and documentation amendment based on
`1d5c6722ecec47bdc69641fd207e8852cf59a3ec`. It does not prove V2
product behavior, authorize V2 implementation, or change the current V1
runtime. It leaves
`v2-execution-spine-2026-07-11.md` unchanged as an immutable record of the
earlier candidate and supersedes only its active execution instructions.

## Repository lifecycle selected

- Program progress is `PLANNING -> READY -> DELIVERY -> INTEGRATION ->
  CUTOVER_ACCEPTED -> CUTOVER_VERIFIED`.
- Program implementation authority is the separate fact `NOT_GRANTED |
  GRANTED`.
- Slice progress is `PLANNED -> READY -> ACTIVE -> CONVERGED -> HANDOFF_READY
  -> ACCEPTED`.
- At this 2026-07-11 reset baseline, the program is `READY`, implementation
  authority is `NOT_GRANTED`, and every slice `010` through `110` is `PLANNED`,
  unassigned, and dormant. V1 remains current. This is the amendment's dated
  snapshot, not a permanent live registry.

This amendment is the durable acceptance of the planning baseline. Its presence
and validity distinguishes program `READY` from `PLANNING`; it is not an
implementation authorization record.

State is derived from each slice declaration plus immutable ordinary-path
activation/acceptance records and append-only candidate/handoff evidence.
There is no central mutable
status, participant, conversation, social, or runtime registry.
After this snapshot, readers resolve live program progress from the umbrella
declaration in `specs/001-nunchi-v2-program/`, implementation authority from
the exact authorization record, and each slice's state and occupant from its
bound declarations plus immutable activation/acceptance records and append-only
candidate/handoff streams. No documentation summary table requires
per-transition maintenance.

## External participant contract

An assigned participant invokes `python3 scripts/run_slice_workflow.py run
nunchi-plan specs/<exact-slice>` for planning or, after all gates can pass,
`python3 scripts/run_slice_workflow.py run speckit specs/<exact-slice>` for
initial delivery, active correction, or rejected-candidate rework. The runner
allowlists and preflights the slice, sets the binding inside the workflow
process, and pins the run's slice; concrete `claude | codex` integration;
integration-manifest digest and exact installed skill bytes; canonical and
persisted workflow digests; initial task-graph digest; resolved inputs; and run
state without modifying `.specify/feature.json`. The persisted workflow must
be byte-identical to the canonical workflow at first binding. The initial
command may append `--integration claude` or `--integration codex`; `auto` is
resolved once before SpecKit persists the input. Resume is only `python3
scripts/run_slice_workflow.py resume <run-id>`; it rejects changed inputs,
workflow content, integration files, run state, or task graph. Any task added
during an initial or resumed run requires a new bound run and is never silently
re-pinned.

Implementation additionally requires the external program-authority record at
`evidence/governance/v2-implementation-authorization.md` to enumerate exactly
all eleven slices `010` through `110`. A partial or extra-scope record is
invalid for every slice. The independent slice-readiness gate then verifies
assignment, accepted dependencies, clean analysis, isolated worktree, and
activation evidence. Each dependent owner separately accepts its required
upstream handoffs before its own slice becomes `READY`. At slice level,
`v2-integrator` accepts slices `010`–`100`, while Zoe accepts slice `110`.
Activation evidence records dependencies as ordered `slice=full-sha` commits
and matching `slice=repo-relative-evidence-file` per-consumer acceptance
references. Slice `110` is not ready until every slice `010`–`100` is itself
`ACCEPTED`.

Zoe, or an assigner named in a durable Zoe delegation, assigns the program
owner and slice occupants. Each declaration uses `<participant identity> —
evidence/governance/assignments/<record>.md`. That record names `Assignee`,
`Lane`, `Assigned by`, `Assigned on`, and `Authority reference`; a non-Zoe
assigner additionally names `Delegated by: Zoe` and `Delegation reference`.
Assignment may precede implementation authority for planning, but does not
grant it or establish `READY`; no assignment registry is created.

Activation freezes `Initial task IDs` and their normalized `Initial tasks
SHA256`. Candidate and handoff evidence are append-only attempt streams. Each
candidate names its exact `Completed task IDs` and current `Tasks SHA256`. A
rejected handoff appends `REJECTED`, the candidate commit, rejecting acceptance
owner, ISO date, and durable decision reference before the same slice returns
to `ACTIVE`. Rework appends new tasks traceable to the rejection, then a new
candidate and handoff; no participant deletes or rewrites the rejected attempt.
Candidate commits exist in Git, and candidate evidence and handoff packets name
exact existing ordinary-path files.

Only slice `110` may assemble the cross-surface candidate. After it reaches
`HANDOFF_READY`, Zoe makes the durable exact-candidate decision. The assigned
`v2-integrator` copies that decision into slice acceptance or rejection
evidence; on acceptance, the assigned `v2-program-owner` copies it into the
program cutover record. That establishes slice `ACCEPTED` and program
`CUTOVER_ACCEPTED`, permitting one atomic merge. The merged docs remain
truthfully marked verification-pending. Verification of the exact resulting
`refs/heads/main` commit plus final documentation validation in a
docs/evidence-only follow-up establishes `CUTOVER_VERIFIED`; release and
promotion remain separate.

The authorization record documents authority granted outside the repository.
It does not grant authority, make a slice ready, or authorize cutover, release,
or promotion.

## Enforced surfaces

- Constitution `2.3.0`, agent guidance, the root README, and the execution-spine
  guide use the same program and slice lifecycle.
- Both SpecKit workflows require one existing `slice_directory` and exact
  binding, and neither has a specification-creation step. The planning cycle
  stops after analysis; the delivery cycle additionally requires implementation
  authority, slice readiness, convergence, documentation freshness, and slice
  handoff.
- Every slice spec, plan, and task list declares its exact binding, state,
  authority, assigned participant/source, and activation-evidence path.
- Governance validation rejects partial or extra authorization scope,
  inconsistent or duplicate declarations, invalid assignment references, weak
  dependency mappings, missing or symlinked terminal evidence, rewritten
  immutable records, truncated append-only attempt history, deleted task
  manifests, checked dormant tasks, missing activation evidence, altered bound
  workflow runs, divergent persisted workflows, changed installed integration
  bytes, aggregate state/occupancy registries, retired local-run terminology in
  active guidance, and integration outside slice `110`.
- Documentation freshness remains a blocking part of every implementation
  slice and every spec implementation must review `README.md` and affected
  ordinary documentation.

## Verification

- `specify workflow info nunchi-plan` parsed `Nunchi Existing-Slice Planning
  Cycle` version `1.4.0` with nine steps, beginning at `bind-existing-slice`,
  with no `speckit.specify` or implementation step.
- `specify workflow info speckit` parsed version `2.5.0` with eighteen steps,
  beginning at `bind-existing-slice` and ending at `slice-handoff`.
- `python3 scripts/check_governance.py --check-cli` passed against SpecKit
  `0.12.11` and its pinned upstream commit.
- `python3 -m unittest` ran 1,054 tests successfully with 8 existing skips.
- `python3 -m evals.verdict_suite.runner --list` discovered all 60 ordinary-path
  V1 regression fixtures.
- `python3 scripts/check_slice_binding.py specs/<exact-slice>` passed for every
  slice `010` through `110`, allowlisted each existing slice, found its required
  artifacts, and verified the exact resolver result without changing
  `.specify/feature.json`.
- Mermaid CLI `11.16.0` rendered all eight Mermaid diagrams in `README.md` and
  `docs/architecture/v2-selected-design.md` successfully.
- A follow-up read-only adversarial review confirmed the initial task graph
  remains immutable across resume, the persisted workflow must equal canonical
  bytes, integration manifests and exact skill files are pinned, workflow
  registry metadata matches the canonical workflow, and checklist identifiers
  are unique.
- `git diff --check` passed, and the active-language audit found no retired
  local-run or obsolete authorization-path wording outside intentional
  test inputs and immutable historical records.
